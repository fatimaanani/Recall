"""Deterministic scene-boundary resolution for a single SearchResult: buffers the matched timestamps, snaps to adjacent transcript segment edges within a merge-gap tolerance, clamps to the video's duration, then enforces min/max clip length centered on the matched interval's own midpoint. No FFmpeg or file I/O here; see clip_service.py for that."""

from __future__ import annotations

import dataclasses

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.search_result import SearchResult
from app.models.transcript_segment import TranscriptSegment
from app.models.video import Video


class InvalidTimestampsError(Exception):
    """matched_start_time/matched_end_time are null, negative, or reversed -- e.g. after the matched transcript segment was removed by a reprocess."""


class MissingDurationError(Exception):
    """Video.duration_seconds is null or non-positive -- can't clamp or
    center a window without a real video length."""


@dataclasses.dataclass(frozen=True)
class ClipInstruction:
    video: Video
    start_time: float
    end_time: float
    duration: float
    # Mirrors VideoOut.media_type's mime_type check; duplicated since that property lives on a Pydantic schema.
    is_audio_only: bool


# "Previous" ends at or before matched_start_time; "next" starts at or after matched_end_time, closest first.
# exclude_id excludes the matched segment itself when its id is known.
def _get_previous_segment(
    db: Session, video_id: int, before_time: float, exclude_id: int | None
) -> TranscriptSegment | None:
    query = db.query(TranscriptSegment).filter(
        TranscriptSegment.video_id == video_id,
        TranscriptSegment.end_time <= before_time,
    )
    if exclude_id is not None:
        query = query.filter(TranscriptSegment.id != exclude_id)
    return query.order_by(TranscriptSegment.end_time.desc()).first()


def _get_next_segment(
    db: Session, video_id: int, after_time: float, exclude_id: int | None
) -> TranscriptSegment | None:
    query = db.query(TranscriptSegment).filter(
        TranscriptSegment.video_id == video_id,
        TranscriptSegment.start_time >= after_time,
    )
    if exclude_id is not None:
        query = query.filter(TranscriptSegment.id != exclude_id)
    return query.order_by(TranscriptSegment.start_time.asc()).first()


# Snaps the buffered edge out to the neighbor segment's far edge when within merge_gap tolerance,
# so the clip never cuts mid-segment. One hop only.
def _snap_start(
    db: Session, video_id: int, raw_start: float, matched_start_time: float,
    exclude_id: int | None, merge_gap: float,
) -> float:
    prev_segment = _get_previous_segment(db, video_id, matched_start_time, exclude_id)
    if prev_segment is None:
        return raw_start
    if abs(raw_start - prev_segment.end_time) <= merge_gap:
        return min(raw_start, prev_segment.start_time)
    return raw_start


def _snap_end(
    db: Session, video_id: int, raw_end: float, matched_end_time: float,
    exclude_id: int | None, merge_gap: float,
) -> float:
    next_segment = _get_next_segment(db, video_id, matched_end_time, exclude_id)
    if next_segment is None:
        return raw_end
    if abs(next_segment.start_time - raw_end) <= merge_gap:
        return max(raw_end, next_segment.end_time)
    return raw_end


# Centers a window of length 2*half_width on `center`, clamped to [0, duration]; if one side
# goes out of bounds, the other compensates to keep the window as close to the target length.
def _centered_window(center: float, half_width: float, duration: float) -> tuple[float, float]:
    start = center - half_width
    end = center + half_width
    if start < 0:
        end = min(duration, end - start)
        start = 0.0
    if end > duration:
        start = max(0.0, start - (end - duration))
        end = duration
    return start, end


def resolve_clip_boundaries(db: Session, result: SearchResult) -> ClipInstruction:
    video = result.video
    settings = get_settings()

    start_time = result.matched_start_time
    end_time = result.matched_end_time
    if start_time is None or end_time is None or end_time < start_time:
        raise InvalidTimestampsError(
            "This result has no resolvable timestamps -- its transcript "
            "segment may have been removed by a reprocess."
        )

    if video.duration_seconds is None or video.duration_seconds <= 0:
        raise MissingDurationError("This video's duration is unknown -- cannot resolve a clip.")

    duration_total = video.duration_seconds

    raw_start = start_time - settings.clip_pre_buffer_seconds
    raw_end = end_time + settings.clip_post_buffer_seconds

    raw_start = _snap_start(
        db, video.id, raw_start, start_time, result.transcript_segment_id,
        settings.clip_max_merge_gap_seconds,
    )
    raw_end = _snap_end(
        db, video.id, raw_end, end_time, result.transcript_segment_id,
        settings.clip_max_merge_gap_seconds,
    )

    clamped_start = max(0.0, raw_start)
    clamped_end = min(duration_total, raw_end)
    if clamped_end < clamped_start:
        # Defensive only; shouldn't happen given validated timestamps, but never produce a negative-length window.
        clamped_end = clamped_start

    match_center = (start_time + end_time) / 2
    window_length = clamped_end - clamped_start

    if window_length < settings.clip_min_duration_seconds:
        if duration_total <= settings.clip_min_duration_seconds:
            # Whole file; never raise for a video shorter than the configured minimum.
            final_start, final_end = 0.0, duration_total
        else:
            final_start, final_end = _centered_window(
                match_center, settings.clip_min_duration_seconds / 2, duration_total
            )
    elif window_length > settings.clip_max_duration_seconds:
        final_start, final_end = _centered_window(
            match_center, settings.clip_max_duration_seconds / 2, duration_total
        )
    else:
        final_start, final_end = clamped_start, clamped_end

    is_audio_only = not video.mime_type.startswith("video/")

    return ClipInstruction(
        video=video,
        start_time=final_start,
        end_time=final_end,
        duration=final_end - final_start,
        is_audio_only=is_audio_only,
    )
