"""
Whisper transcription and hallucination-filtering logic, shared by both
the upload pipeline (media_processing_service.py) and the search-query
audio pipeline (search_service.py) so both can call the same validation
without a service-to-service import between them.
"""

from __future__ import annotations

import difflib
import logging
import multiprocessing
import pathlib
import queue as queue_module
import re
import subprocess
import threading
from dataclasses import dataclass

from app.config import get_settings
from app.processing.ffmpeg_processor import ProcessingError

settings = get_settings()
logger = logging.getLogger(__name__)

# One transcription at a time, process-wide
_transcription_lock = threading.Lock()


@dataclass(frozen=True)
class WhisperSegment:
    start: float
    end: float
    text: str
    no_speech_prob: float
    avg_logprob: float
    # Repetition/hallucination heuristic
    compression_ratio: float


_MIN_SEGMENTS_FOR_REPETITION_CHECK = 3


def segment_words_per_second(segment: WhisperSegment) -> float:
    duration = segment.end - segment.start
    if duration <= 0:
        return 0.0
    return len(segment.text.split()) / duration


def _non_no_speech_failure_reasons(segment: WhisperSegment) -> list[str]:
    reasons = []
    if segment.avg_logprob < settings.whisper_min_avg_logprob:
        reasons.append(
            f"avg_logprob {segment.avg_logprob:.3f} < min {settings.whisper_min_avg_logprob}"
        )
    if segment.compression_ratio > settings.whisper_max_compression_ratio:
        reasons.append(
            f"compression_ratio {segment.compression_ratio:.3f} > max {settings.whisper_max_compression_ratio}"
        )
    wps = segment_words_per_second(segment)
    if wps > settings.whisper_max_words_per_second:
        reasons.append(f"words_per_second {wps:.2f} > max {settings.whisper_max_words_per_second}")
    return reasons


# Accept/reject a segment: "relief" lets a high no_speech_prob through if
# every other signal is clean.
def evaluate_segment(segment: WhisperSegment) -> tuple[bool, str, list[str]]:
    text = segment.text.strip()
    if not text:
        return False, "rejected", ["blank text"]

    other_reasons = _non_no_speech_failure_reasons(segment)
    no_speech_over_soft = segment.no_speech_prob > settings.whisper_max_no_speech_prob

    if not no_speech_over_soft:
        if other_reasons:
            return False, "rejected", other_reasons
        return True, "normal", []

    # Beyond here no_speech_prob exceeds the soft ceiling, so relief is only possible if other signals are clean.
    if other_reasons:
        reasons = list(other_reasons)
        reasons.append(
            f"no_speech_prob {segment.no_speech_prob:.3f} > max {settings.whisper_max_no_speech_prob}"
        )
        return False, "rejected", reasons

    if segment.no_speech_prob > settings.whisper_hard_max_no_speech_prob:
        return False, "rejected", [
            f"no_speech_prob {segment.no_speech_prob:.3f} > hard ceiling "
            f"{settings.whisper_hard_max_no_speech_prob} (relief not eligible)"
        ]

    return True, "relief", [
        f"no_speech_prob {segment.no_speech_prob:.3f} > soft max {settings.whisper_max_no_speech_prob} "
        f"but <= hard ceiling {settings.whisper_hard_max_no_speech_prob}; avg_logprob/compression_ratio/"
        f"words_per_second all clean"
    ]


def _normalize_segment_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def is_hallucination_dominated(segments: list[WhisperSegment]) -> bool:
    if len(segments) < _MIN_SEGMENTS_FOR_REPETITION_CHECK:
        return False

    clusters: list[list] = []  # [normalized_representative_text, count]
    for segment in segments:
        normalized = _normalize_segment_text(segment.text)
        for cluster in clusters:
            if difflib.SequenceMatcher(None, normalized, cluster[0]).ratio() >= settings.whisper_repetition_similarity:
                cluster[1] += 1
                break
        else:
            clusters.append([normalized, 1])

    largest_cluster_size = max(count for _, count in clusters)
    return (largest_cluster_size / len(segments)) >= settings.whisper_max_repetition_ratio


# FFmpeg audio extraction, mono 16kHz WAV
def extract_audio(source_path: pathlib.Path, dest_path: pathlib.Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        settings.ffmpeg_binary,
        "-y",  # overwrite dest_path if a previous attempt left one behind
        "-i", str(source_path),
        "-vn",  # drop any video stream, audio only
        "-ac", "1",  # mono
        "-ar", "16000",  # 16kHz
        "-f", "wav",
        str(dest_path),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.ffmpeg_timeout_seconds,
            check=True,
        )
    except FileNotFoundError:
        raise ProcessingError(
            f"'{settings.ffmpeg_binary}' was not found -- is FFmpeg installed and on PATH?"
        )
    except subprocess.TimeoutExpired:
        raise ProcessingError("Extracting audio took too long and was aborted.")
    except subprocess.CalledProcessError as exc:
        raise ProcessingError(
            f"ffmpeg could not extract an audio track from this file: {exc.stderr.strip()[:300]}"
        )

    if not dest_path.exists():
        raise ProcessingError("ffmpeg reported success but no audio file was produced.")


# Whisper transcription, runs in a subprocess
def _whisper_worker(
    audio_path: str,
    model_size: str,
    device: str,
    compute_type: str,
    result_queue: "multiprocessing.Queue",
) -> None:
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _info = model.transcribe(
            audio_path,
            beam_size=5,
            language=None,
            condition_on_previous_text=False,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            vad_filter=False,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        raw = [
            (
                segment.start,
                segment.end,
                segment.text,
                segment.no_speech_prob,
                segment.avg_logprob,
                segment.compression_ratio,
            )
            for segment in segments
        ]
        result_queue.put(("ok", raw))
    except Exception as exc:  # noqa: BLE001, reported to the parent, never raised here
        result_queue.put(("error", str(exc)))


def _terminate_worker(process: "multiprocessing.Process") -> None:
    process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)


# timeout_seconds defaults to the 2-hour video-pipeline setting; the
# query pipeline (search_service.py) passes its own, much shorter timeout
# explicitly, since a live HTTP request shouldn't wait anywhere near that long.
def transcribe_audio(
    audio_path: pathlib.Path, timeout_seconds: float | None = None
) -> list[WhisperSegment]:
    effective_timeout = (
        timeout_seconds if timeout_seconds is not None else settings.whisper_transcription_timeout_seconds
    )
    with _transcription_lock:
        result_queue: multiprocessing.Queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_whisper_worker,
            args=(
                str(audio_path),
                settings.whisper_model_size,
                settings.whisper_device,
                settings.whisper_compute_type,
                result_queue,
            ),
        )
        process.start()

        try:
            # queue.get(timeout=...) rather than process.join(timeout=...), since
            # join() can lag behind the moment a result is actually ready.
            outcome = result_queue.get(timeout=effective_timeout)
        except queue_module.Empty:
            _terminate_worker(process)
            raise ProcessingError(
                "Whisper transcription exceeded the configured timeout of "
                f"{effective_timeout} seconds and was aborted."
            )

        # Let the already-finished worker exit normally rather than leaving a zombie.
        process.join(timeout=5)

        status, payload = outcome
        if status == "error":
            raise ProcessingError(f"Whisper transcription failed: {payload}")
        raw_segments = payload

    raw_count = len(raw_segments)
    blank_count = 0
    results = []
    for start, end, text, no_speech_prob, avg_logprob, compression_ratio in raw_segments:
        text = text.strip()
        if not text:
            blank_count += 1
            continue
        results.append(
            WhisperSegment(
                start=start,
                end=end,
                text=text,
                no_speech_prob=no_speech_prob,
                avg_logprob=avg_logprob,
                compression_ratio=compression_ratio,
            )
        )

    logger.debug(
        "whisper transcribe result: model_size=%s device=%s compute_type=%s "
        "raw_segments=%d blank_dropped=%d non_blank_segments=%d",
        settings.whisper_model_size, settings.whisper_device, settings.whisper_compute_type,
        raw_count, blank_count, len(results),
    )
    return results
