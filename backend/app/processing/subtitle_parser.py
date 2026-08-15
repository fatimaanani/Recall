"""
Parses SRT and VTT subtitle text into transcript_segmenter.RawCue objects,
the same shape Whisper's own output is adapted to, so both subtitle and
Whisper segments flow through the same segment_cues() merge/split stage.

Hand-rolled rather than using a third-party subtitle library since both
formats' cue structure is simple enough not to justify the dependency.

Never invents text: every non-blank text line inside a cue is kept,
joined with a single space if a cue spans multiple lines. VTT
cue-settings lines and SRT index lines are structural metadata and are
discarded.
"""

from __future__ import annotations

import re

from app.processing.transcript_segmenter import RawCue

_SRT_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)
_VTT_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)


class SubtitleParseError(Exception):
    """Raised when a file passed upload-time validation but yields no
    parseable cues at processing time; callers fall back to Whisper
    rather than failing the video."""


def _timestamp_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _parse_blocks(text: str, timestamp_re: re.Pattern[str]) -> list[RawCue]:
    cues: list[RawCue] = []
    # Blocks are separated by blank lines; line endings are normalized first.
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))

    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        timestamp_line_index = None
        for index, line in enumerate(lines):
            if timestamp_re.search(line):
                timestamp_line_index = index
                break
        if timestamp_line_index is None:
            # No timestamp in this block (e.g. VTT's leading "WEBVTT" header) -- not a cue.
            continue

        match = timestamp_re.search(lines[timestamp_line_index])
        start = _timestamp_to_seconds(*match.group(1, 2, 3, 4))
        end = _timestamp_to_seconds(*match.group(5, 6, 7, 8))

        text_lines = lines[timestamp_line_index + 1:]
        cue_text = " ".join(line.strip() for line in text_lines).strip()
        if not cue_text:
            continue  # blank cue (e.g. a music-only marker) -- nothing searchable to keep

        cues.append(RawCue(start=start, end=end, text=cue_text))

    return cues


def parse_srt(text: str) -> list[RawCue]:
    return _parse_blocks(text, _SRT_TIMESTAMP_RE)


def parse_vtt(text: str) -> list[RawCue]:
    return _parse_blocks(text, _VTT_TIMESTAMP_RE)


def parse_subtitle_file(extension: str, text: str) -> list[RawCue]:
    """`extension` is "srt" or "vtt", already validated at upload time.
    Raises SubtitleParseError if the result is empty."""
    if extension == "srt":
        cues = parse_srt(text)
    elif extension == "vtt":
        cues = parse_vtt(text)
    else:
        raise SubtitleParseError(f"Unsupported subtitle extension: {extension!r}")

    if not cues:
        raise SubtitleParseError("No usable subtitle cues were found in this file.")
    return cues
