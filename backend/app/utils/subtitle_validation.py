"""
Upload-time validation for a user-supplied subtitle file (SRT/VTT),
mirroring file_validation.py's extension-allowlist approach. Since
subtitle files are plain text, "signature" here means the first
non-empty line matching the format's own required header/structure,
not a binary magic number.
"""

from __future__ import annotations

import re

ALLOWED_SUBTITLE_EXTENSIONS: dict[str, str] = {
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
}

# SRT uses a comma for milliseconds, VTT a period; a well-formed timestamp
# line is the real structural signal against a stray extension.
_SRT_TIMESTAMP_RE = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")
_VTT_TIMESTAMP_RE = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")


class InvalidSubtitleFileError(Exception):
    pass


def extract_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def validate_subtitle_upload(filename: str, content: bytes, max_size_bytes: int) -> str:
    """Returns the validated extension. Deliberately not a full parse
    (subtitle_parser.py does that later) -- just enough to reject an
    obviously-wrong upload immediately."""
    extension = extract_extension(filename)
    if extension not in ALLOWED_SUBTITLE_EXTENSIONS:
        raise InvalidSubtitleFileError(
            f"'.{extension or '?'}' is not a supported subtitle file type. Use .srt or .vtt."
        )

    if len(content) == 0:
        raise InvalidSubtitleFileError("The subtitle file is empty.")
    if len(content) > max_size_bytes:
        raise InvalidSubtitleFileError(
            f"Subtitle file exceeds the {max_size_bytes // 1024} KiB limit."
        )

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidSubtitleFileError("The subtitle file must be UTF-8 encoded text.")

    if extension == "srt":
        if not _SRT_TIMESTAMP_RE.search(text):
            raise InvalidSubtitleFileError(
                "This doesn't look like a valid .srt file (no timestamp line found)."
            )
    else:  # vtt
        lines = text.splitlines()
        first_line = lines[0].strip() if lines else ""
        if not first_line.startswith("WEBVTT"):
            raise InvalidSubtitleFileError("This doesn't look like a valid .vtt file (missing WEBVTT header).")
        if not _VTT_TIMESTAMP_RE.search(text):
            raise InvalidSubtitleFileError(
                "This doesn't look like a valid .vtt file (no timestamp line found)."
            )

    return extension
