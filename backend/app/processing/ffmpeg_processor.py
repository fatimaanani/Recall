# FFmpeg/ffprobe subprocess wrappers

from __future__ import annotations

import json
import pathlib
import subprocess

from app.config import get_settings

settings = get_settings()


# ffmpeg/ffprobe failure
class ProcessingError(Exception):
    pass


# ffprobe duration lookup
def probe_duration_seconds(file_path: pathlib.Path) -> float:
    command = [
        settings.ffprobe_binary,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.ffmpeg_timeout_seconds,
            check=True,
        )
    except FileNotFoundError:
        raise ProcessingError(
            f"'{settings.ffprobe_binary}' was not found -- is FFmpeg installed and on PATH?"
        )
    except subprocess.TimeoutExpired:
        raise ProcessingError("Reading this file's duration took too long and was aborted.")
    except subprocess.CalledProcessError as exc:
        raise ProcessingError(f"ffprobe could not read this file: {exc.stderr.strip()[:300]}")

    output = result.stdout.strip()
    try:
        return float(output)
    except ValueError:
        raise ProcessingError(f"ffprobe returned an unreadable duration: {output!r}")


# Returns None rather than raising on failure, since detection is a
# best-effort step in the upload > embedded > Whisper precedence -- a
# failed probe just falls through to Whisper.
_EXTRACTABLE_SUBTITLE_CODECS = {"subrip", "ass", "ssa", "mov_text", "webvtt"}


def probe_embedded_subtitle_stream_index(file_path: pathlib.Path) -> int | None:
    command = [
        settings.ffprobe_binary,
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name",
        "-of", "json",
        str(file_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.ffmpeg_timeout_seconds,
            check=True,
        )
        streams = json.loads(result.stdout).get("streams", [])
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return None

    for stream in streams:
        if stream.get("codec_name") in _EXTRACTABLE_SUBTITLE_CODECS:
            index = stream.get("index")
            if isinstance(index, int):
                return index
    return None


# Stream-copies the subtitle track only (-c:s srt), never transcoding.
# Raises on failure, unlike the probe above, since the caller falls back
# to Whisper if extraction fails.
def extract_embedded_subtitle(source_path: pathlib.Path, dest_path: pathlib.Path, stream_index: int) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-i", str(source_path),
        "-map", f"0:{stream_index}",
        "-c:s", "srt",
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
        raise ProcessingError("Extracting the embedded subtitle track took too long and was aborted.")
    except subprocess.CalledProcessError as exc:
        raise ProcessingError(f"ffmpeg could not extract the embedded subtitle track: {exc.stderr.strip()[:300]}")

    if not dest_path.exists() or dest_path.stat().st_size == 0:
        dest_path.unlink(missing_ok=True)
        raise ProcessingError("ffmpeg reported success but no subtitle file was produced.")


# ffmpeg thumbnail extraction, video only
def generate_thumbnail(video_path: pathlib.Path, thumbnail_path: pathlib.Path, at_second: float) -> None:
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        settings.ffmpeg_binary,
        "-y",  # overwrite thumbnail_path if it somehow already exists
        "-ss", str(max(at_second, 0)),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "3",  # JPEG quality scale, 2-5 is visually good without a huge file
        str(thumbnail_path),
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
        raise ProcessingError("Generating a thumbnail took too long and was aborted.")
    except subprocess.CalledProcessError as exc:
        raise ProcessingError(f"ffmpeg could not generate a thumbnail: {exc.stderr.strip()[:300]}")

    if not thumbnail_path.exists():
        raise ProcessingError("ffmpeg reported success but no thumbnail file was produced.")


# Always transcodes rather than stream-copying, since source uploads
# (MKV/WEBM) aren't valid inside MP4 without it.
def generate_clip(
    source_path: pathlib.Path,
    output_path: pathlib.Path,
    start_time: float,
    end_time: float,
    is_audio_only: bool,
    timeout_seconds: float | None = None,
) -> None:
    effective_timeout = timeout_seconds if timeout_seconds is not None else settings.ffmpeg_timeout_seconds
    clip_duration = end_time - start_time
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if is_audio_only:
        # MP3 via libmp3lame for universal browser playback regardless of source codec.
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-ss", str(max(start_time, 0)),
            "-i", str(source_path),
            "-t", str(clip_duration),
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_path),
        ]
    else:
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-ss", str(max(start_time, 0)),
            "-i", str(source_path),
            "-t", str(clip_duration),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(output_path),
        ]

    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=True,
        )
    except FileNotFoundError:
        output_path.unlink(missing_ok=True)
        raise ProcessingError(
            f"'{settings.ffmpeg_binary}' was not found -- is FFmpeg installed and on PATH?"
        )
    except subprocess.TimeoutExpired:
        output_path.unlink(missing_ok=True)
        raise ProcessingError("Generating this clip took too long and was aborted.")
    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        raise ProcessingError(f"ffmpeg could not generate this clip: {exc.stderr.strip()[:300]}")

    # Never leave a zero-byte or missing file behind as if it succeeded.
    if not output_path.exists() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise ProcessingError("ffmpeg reported success but no valid clip file was produced.")
