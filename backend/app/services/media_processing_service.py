"""Handles the video processing pipeline: metadata extraction, transcript generation (uploaded/embedded subtitle or Whisper), and embedding generation. Whisper hallucination-filtering/validation helpers live in app/processing/whisper_processor.py."""

from __future__ import annotations

import datetime
import logging
import pathlib
import threading
import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.enums import MediaStatus, ProcessingStatus, SubtitleSource
from app.models.processing_log import ProcessingLog
from app.models.transcript_segment import TranscriptSegment
from app.models.video import Video
from app.processing import embedding_processor, subtitle_parser, transcript_segmenter, whisper_processor
from app.processing.ffmpeg_processor import (
    ProcessingError,
    extract_embedded_subtitle,
    generate_thumbnail,
    probe_duration_seconds,
    probe_embedded_subtitle_stream_index,
)
from app.processing.transcript_segmenter import RawCue
from app.services import elasticsearch_service, error_log_service
from app.utils.subtitle_validation import extract_extension as extract_subtitle_extension

settings = get_settings()
logger = logging.getLogger(__name__)

PROCESS_TYPE_METADATA = "metadata_extraction"
# Kept as "whisper_transcription" even though this stage may resolve an uploaded or embedded
# subtitle instead of running Whisper -- the frontend Upload Queue keys off this exact string.
PROCESS_TYPE_TRANSCRIPT = "whisper_transcription"
PROCESS_TYPE_EMBEDDING = "embedding_generation"

# Ensures a startup-triggered and admin-triggered backfill run can never overlap.
_backfill_lock = threading.Lock()


def process_video(video_id: int) -> None:
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video is None:
            # Deleted (or never existed) by the time this ran, nothing to do.
            return

        video.status = MediaStatus.PROCESSING
        db.commit()

        metadata_log = _start_stage(db, video, PROCESS_TYPE_METADATA)
        try:
            _extract_metadata(video)
        except ProcessingError as exc:
            db.rollback()
            _mark_failed(db, video, metadata_log, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- catch-all so an unexpected error still fails the video cleanly
            db.rollback()
            _mark_failed(db, video, metadata_log, f"Unexpected processing error: {exc}", log_exception=True)
            return
        _complete_stage(db, metadata_log)

        whisper_log = _start_stage(db, video, PROCESS_TYPE_TRANSCRIPT)
        try:
            removed_segment_ids = _generate_transcript(db, video)
        except ProcessingError as exc:
            db.rollback()
            _mark_failed(db, video, whisper_log, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- same catch-all as above
            db.rollback()
            _mark_failed(db, video, whisper_log, f"Unexpected processing error: {exc}", log_exception=True)
            return
        _complete_stage(db, whisper_log)
        # Evaluation-only, best-effort; never affects video.status.
        _sync_elasticsearch_reindex(db, video, removed_segment_ids)

        # Embedding is best-effort: Exact Text search doesn't need it, and Speech-to-Text only needs
        # it for its semantic sub-path, so failure here doesn't fail the whole video; it's recorded
        # on its own log row for retry_missing_embeddings.
        embedding_log = _start_stage(db, video, PROCESS_TYPE_EMBEDDING)
        try:
            _generate_embeddings_for_video(db, video)
        except ProcessingError as exc:
            db.rollback()
            _mark_embedding_failed(db, video, embedding_log, str(exc))
        except Exception as exc:  # noqa: BLE001 -- same catch-all as above
            db.rollback()
            _mark_embedding_failed(db, video, embedding_log, f"Unexpected processing error: {exc}", log_exception=True)
        else:
            _complete_stage(db, embedding_log)

        video.status = MediaStatus.READY
        video.processing_error = None
        db.commit()
    finally:
        db.close()


def recover_orphaned_processing_videos(db: Session) -> int:
    orphaned_videos = db.query(Video).filter(Video.status == MediaStatus.PROCESSING).all()
    for video in orphaned_videos:
        message = "Processing was interrupted by a backend restart and could not resume automatically."
        video.status = MediaStatus.FAILED
        video.processing_error = message

        started_log = (
            db.query(ProcessingLog)
            .filter(ProcessingLog.video_id == video.id, ProcessingLog.status == ProcessingStatus.STARTED)
            .order_by(ProcessingLog.started_at.desc())
            .first()
        )
        if started_log is not None:
            started_log.status = ProcessingStatus.FAILED
            started_log.message = message
            started_log.completed_at = datetime.datetime.utcnow()

        logger.warning("Recovered orphaned PROCESSING video %s at startup -- marked FAILED.", video.id)

    if orphaned_videos:
        db.commit()

    return len(orphaned_videos)


def _start_stage(db: Session, video: Video, process_type: str) -> ProcessingLog:
    log = ProcessingLog(
        video_id=video.id,
        process_type=process_type,
        status=ProcessingStatus.STARTED,
        started_at=datetime.datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    return log


def _complete_stage(db: Session, log: ProcessingLog) -> None:
    log.status = ProcessingStatus.COMPLETED
    log.completed_at = datetime.datetime.utcnow()
    db.commit()


def _mark_failed(db: Session, video: Video, log: ProcessingLog, message: str, log_exception: bool = False) -> None:
    video.status = MediaStatus.FAILED
    video.processing_error = message
    log.status = ProcessingStatus.FAILED
    log.message = message
    log.completed_at = datetime.datetime.utcnow()
    if log_exception:
        logger.exception("Unexpected error processing video %s (%s)", video.id, log.process_type)
    else:
        logger.warning("Processing failed for video %s (%s): %s", video.id, log.process_type, message)
    db.commit()


# Deliberately separate from _mark_failed: never touches video.status, since embedding failure doesn't fail the whole video.
def _mark_embedding_failed(
    db: Session, video: Video, log: ProcessingLog, message: str, log_exception: bool = False
) -> None:
    log.status = ProcessingStatus.FAILED
    log.message = message
    log.completed_at = datetime.datetime.utcnow()
    if log_exception:
        logger.exception("Unexpected error generating embeddings for video %s", video.id)
    else:
        logger.warning("Embedding generation failed for video %s: %s", video.id, message)
    db.commit()


# Evaluation-only, best-effort: swallows every exception so a missing/unreachable
# Elasticsearch can never affect a real upload.
def _sync_elasticsearch_reindex(db: Session, video: Video, removed_segment_ids: list[int]) -> None:
    try:
        for segment_id in removed_segment_ids:
            try:
                elasticsearch_service.delete_segment(segment_id)
            except elasticsearch_service.ElasticsearchUnavailableError:
                # Disabled/unreachable is the expected default state; nothing to log.
                return

        fresh_segments = db.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).all()
        for segment in fresh_segments:
            elasticsearch_service.index_segment(segment, video)
    except elasticsearch_service.ElasticsearchUnavailableError:
        return
    except Exception as exc:  # noqa: BLE001 -- evaluation-only sync must never affect real processing
        logger.warning("Elasticsearch sync failed for video %s: %s", video.id, exc)
        error_log_service.log_error(db, error_source="elasticsearch_sync", error_message=str(exc), video_id=video.id)


def _extract_metadata(video: Video) -> None:
    source_path = pathlib.Path(settings.storage_root) / video.file_path
    if not source_path.exists():
        raise ProcessingError("The uploaded file is missing from storage.")

    duration = probe_duration_seconds(source_path)
    video.duration_seconds = duration

    if video.mime_type.startswith("video/"):
        thumbnail_rel_path = pathlib.Path("thumbnails") / str(video.owner_id) / f"{uuid.uuid4().hex}.jpg"
        thumbnail_full_path = pathlib.Path(settings.storage_root) / thumbnail_rel_path
        # Grab frame at halfway point, not the blank intro frame
        at_second = min(1.0, duration / 2) if duration > 0 else 0
        generate_thumbnail(source_path, thumbnail_full_path, at_second)
        video.thumbnail_path = str(thumbnail_rel_path)


# Extracts audio, transcribes, and hallucination-filters; never touches the database. Raises
# ProcessingError if no reliable speech is found -- the last fallback in the source precedence
# chain, so failure here is a genuine whole-video failure.
def _whisper_transcribe_to_cues(video: Video, source_path: pathlib.Path) -> list[RawCue]:
    temp_dir = pathlib.Path(settings.processing_temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_audio_path = temp_dir / f"{uuid.uuid4().hex}.wav"

    try:
        whisper_processor.extract_audio(source_path, temp_audio_path)
        segments = whisper_processor.transcribe_audio(temp_audio_path)
    finally:
        temp_audio_path.unlink(missing_ok=True)

    if not segments:
        raise ProcessingError("No speech detected. A searchable transcript could not be generated.")

    reliable_segments = []
    normal_count = 0
    relief_count = 0
    rejected_count = 0
    for segment in segments:
        accepted, path, reasons = whisper_processor.evaluate_segment(segment)
        wps = whisper_processor.segment_words_per_second(segment)
        if path == "normal":
            normal_count += 1
            logger.debug(
                "video %s: PASSED-NORMAL [%.2f-%.2f] text=%r no_speech_prob=%.3f avg_logprob=%.3f "
                "compression_ratio=%.3f words_per_second=%.2f",
                video.id, segment.start, segment.end, segment.text,
                segment.no_speech_prob, segment.avg_logprob, segment.compression_ratio, wps,
            )
        elif path == "relief":
            relief_count += 1
            logger.debug(
                "video %s: PASSED-RELIEF [%.2f-%.2f] text=%r no_speech_prob=%.3f avg_logprob=%.3f "
                "compression_ratio=%.3f words_per_second=%.2f note=%s",
                video.id, segment.start, segment.end, segment.text,
                segment.no_speech_prob, segment.avg_logprob, segment.compression_ratio, wps, reasons,
            )
        else:
            rejected_count += 1
            logger.debug(
                "video %s: REJECTED [%.2f-%.2f] text=%r no_speech_prob=%.3f avg_logprob=%.3f "
                "compression_ratio=%.3f words_per_second=%.2f reasons=%s",
                video.id, segment.start, segment.end, segment.text,
                segment.no_speech_prob, segment.avg_logprob, segment.compression_ratio, wps, reasons,
            )
        if accepted:
            reliable_segments.append(segment)

    logger.debug(
        "video %s: validation summary -- %d normal, %d relief, %d rejected (of %d total)",
        video.id, normal_count, relief_count, rejected_count, len(segments),
    )

    if not reliable_segments or whisper_processor.is_hallucination_dominated(reliable_segments):
        if reliable_segments:
            logger.debug(
                "video %s: %d reliable segments rejected as hallucination-dominated (repetition ratio >= %s)",
                video.id, len(reliable_segments), settings.whisper_max_repetition_ratio,
            )
        raise ProcessingError("No reliable speech detected. A searchable transcript could not be generated.")

    return [RawCue(start=seg.start, end=seg.end, text=seg.text) for seg in reliable_segments]


# video.subtitle_path is already set by video_service.save_upload at upload time. Returns None
# (not raises) on failure, so _generate_transcript falls through to the next source; the failure
# is still logged.
def _try_uploaded_subtitle_cues(db: Session, video: Video) -> list[RawCue] | None:
    if video.subtitle_source != SubtitleSource.UPLOADED or not video.subtitle_path:
        return None
    abs_path = pathlib.Path(settings.storage_root) / video.subtitle_path
    try:
        text = abs_path.read_text(encoding="utf-8-sig")
        extension = extract_subtitle_extension(video.subtitle_path)
        return subtitle_parser.parse_subtitle_file(extension, text)
    except (OSError, UnicodeDecodeError, subtitle_parser.SubtitleParseError) as exc:
        error_log_service.log_error(
            db, error_source="subtitle_processing", error_message=str(exc), video_id=video.id
        )
        return None


# Probes the source file for a text-based subtitle stream; if found, extracts it to its own .srt
# and sets video.subtitle_path, same as an uploaded one. Same "return None, log, fall through"
# contract as the uploaded branch above.
def _try_embedded_subtitle_cues(db: Session, video: Video, source_path: pathlib.Path) -> list[RawCue] | None:
    try:
        stream_index = probe_embedded_subtitle_stream_index(source_path)
    except Exception as exc:  # noqa: BLE001 -- probing is best-effort, never fatal
        error_log_service.log_error(
            db, error_source="subtitle_processing", error_message=str(exc), video_id=video.id
        )
        return None
    if stream_index is None:
        return None

    extract_dir = pathlib.Path(settings.storage_root) / "subtitles" / str(video.owner_id)
    extract_dir.mkdir(parents=True, exist_ok=True)
    disk_filename = f"{uuid.uuid4().hex}.srt"
    abs_path = extract_dir / disk_filename
    try:
        extract_embedded_subtitle(source_path, abs_path, stream_index)
        text = abs_path.read_text(encoding="utf-8-sig")
        cues = subtitle_parser.parse_subtitle_file("srt", text)
    except (ProcessingError, OSError, UnicodeDecodeError, subtitle_parser.SubtitleParseError) as exc:
        abs_path.unlink(missing_ok=True)
        error_log_service.log_error(
            db, error_source="subtitle_processing", error_message=str(exc), video_id=video.id
        )
        return None

    # Only recorded on success, so a failed extraction never leaves a dangling subtitle_path.
    video.subtitle_path = str(pathlib.Path("subtitles") / str(video.owner_id) / disk_filename)
    return cues


# Source precedence: uploaded subtitle > embedded subtitle > Whisper. Deletes and replaces ALL
# existing segments regardless of prior source, since exactly one source is ever active for a
# video at a time. Returns the ids of any deleted segments so the caller can keep the
# Elasticsearch evaluation index in sync.
def _generate_transcript(db: Session, video: Video) -> list[int]:
    source_path = pathlib.Path(settings.storage_root) / video.file_path
    if not source_path.exists():
        raise ProcessingError("The uploaded file is missing from storage.")

    raw_cues = _try_uploaded_subtitle_cues(db, video)
    source_used = SubtitleSource.UPLOADED if raw_cues is not None else None

    if raw_cues is None:
        raw_cues = _try_embedded_subtitle_cues(db, video, source_path)
        source_used = SubtitleSource.EMBEDDED if raw_cues is not None else None

    if raw_cues is None:
        raw_cues = _whisper_transcribe_to_cues(video, source_path)  # raises ProcessingError if nothing usable
        source_used = SubtitleSource.WHISPER

    # Captured before the delete below, since it's not derivable afterward; lets the
    # Elasticsearch evaluation index remove stale documents too.
    removed_segment_ids = [
        row.id
        for row in db.query(TranscriptSegment.id).filter(TranscriptSegment.video_id == video.id).all()
    ]

    db.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).delete(synchronize_session=False)
    # Deleting the segments deletes their embeddings with them; reset the flag so a stale True
    # can't linger if this video is re-transcribed.
    video.has_embeddings = False

    # Raw cues are often fragmented (split across near-zero-gap segments or short subtitle cues);
    # this merges them and splits the rare overlong one.
    cleaned_cues = transcript_segmenter.segment_cues(
        raw_cues,
        merge_gap_seconds=settings.transcript_segment_merge_gap_seconds,
        max_merged_duration_seconds=settings.transcript_segment_max_merged_duration_seconds,
        max_duration_seconds=settings.transcript_segment_max_duration_seconds,
    )

    for cue in cleaned_cues:
        db.add(
            TranscriptSegment(
                video_id=video.id,
                start_time=cue.start,
                end_time=cue.end,
                text=cue.text,
                source=source_used,
            )
        )

    video.has_subtitles = True
    video.subtitle_source = source_used
    return removed_segment_ids


# One batched model.encode() call for all of this video's segments.
def _generate_embeddings_for_video(db: Session, video: Video) -> None:
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video.id)
        .order_by(TranscriptSegment.id)
        .all()
    )
    if not segments:
        # Not expected from process_video (which always raises earlier if no segments were
        # persisted), but retry_missing_embeddings could reach a video with none removed some
        # other way -- vacuously "fully embedded" so it isn't retried forever.
        video.has_embeddings = True
        return

    texts = [segment.text for segment in segments]
    vectors = embedding_processor.generate_embeddings(texts)

    # Assigned in memory only; the caller commits this with the ProcessingLog update in one
    # transaction, so a video is never left partially embedded.
    for segment, vector in zip(segments, vectors):
        segment.embedding = vector

    video.has_embeddings = True


# Covers both a failed embedding stage and a video uploaded before this feature existed;
# has_embeddings defaults to False either way. Guarded by _backfill_lock (in-memory, per-process)
# so a startup-triggered and admin-triggered run can never overlap -- sufficient since this runs
# as a single backend process, not distributed.
def retry_missing_embeddings(db: Session) -> int:
    if not _backfill_lock.acquire(blocking=False):
        logger.info("Embedding backfill already in progress in this process, skipping this run.")
        return 0

    try:
        videos = (
            db.query(Video)
            .filter(Video.status == MediaStatus.READY, Video.has_embeddings.is_(False))
            .all()
        )

        processed_count = 0
        for video in videos:
            # Re-check right before processing, closing the race against a normal upload's
            # embedding stage completing this video concurrently.
            db.refresh(video)
            if video.has_embeddings:
                continue

            embedding_log = _start_stage(db, video, PROCESS_TYPE_EMBEDDING)
            try:
                _generate_embeddings_for_video(db, video)
            except ProcessingError as exc:
                db.rollback()
                _mark_embedding_failed(db, video, embedding_log, str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 -- same catch-all as process_video
                db.rollback()
                _mark_embedding_failed(
                    db, video, embedding_log, f"Unexpected processing error: {exc}", log_exception=True
                )
                continue
            _complete_stage(db, embedding_log)
            processed_count += 1

        return processed_count
    finally:
        _backfill_lock.release()


# Shared entry point for both backfill triggers; owns its own SessionLocal() since it runs
# detached from a background thread that may already be gone by the time this finishes.
def backfill_missing_embeddings_task() -> None:
    db = SessionLocal()
    try:
        processed_count = retry_missing_embeddings(db)
        if processed_count:
            logger.info("Embedding backfill: generated embeddings for %d video(s).", processed_count)
    except Exception:  # noqa: BLE001 -- a background task's exception would otherwise vanish silently
        logger.exception("Embedding backfill failed unexpectedly.")
    finally:
        db.close()
