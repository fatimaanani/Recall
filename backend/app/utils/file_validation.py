from __future__ import annotations

ALLOWED_VIDEO_EXTENSIONS: dict[str, str] = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "webm": "video/webm",
}
ALLOWED_AUDIO_EXTENSIONS: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
}
ALLOWED_EXTENSIONS: dict[str, str] = {**ALLOWED_VIDEO_EXTENSIONS, **ALLOWED_AUDIO_EXTENSIONS}


# Unsupported extension or signature mismatch
class UnsupportedFileTypeError(Exception):
    pass


def extract_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _matches_known_signature(extension: str, head: bytes) -> bool:
    if extension in ("mp4", "mov", "m4a"):
        # ISO base media format (MP4/QuickTime/M4A share it): box size then literal "ftyp" at offset 4.
        return head[4:8] == b"ftyp"
    if extension == "mkv" or extension == "webm":
        # Both are EBML containers sharing this exact 4-byte signature.
        return head[:4] == b"\x1a\x45\xdf\xa3"
    if extension == "wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if extension == "flac":
        return head[:4] == b"fLaC"
    if extension == "mp3":
        # Most mp3s carry an ID3v2 tag first; a bare mp3 instead starts with a frame sync (0xFF + top 3 bits set).
        return head[:3] == b"ID3" or (head[0:1] == b"\xff" and (head[1] & 0xE0) == 0xE0)
    return False


def validate_upload(filename: str, head: bytes) -> tuple[str, str]:
    extension = extract_extension(filename)
    mime_type = ALLOWED_EXTENSIONS.get(extension)
    if mime_type is None:
        raise UnsupportedFileTypeError(
            f"'.{extension or '?'}' is not a supported video or audio file type."
        )
    if not _matches_known_signature(extension, head):
        raise UnsupportedFileTypeError(
            f"This file's content doesn't match a valid .{extension} file."
        )
    return extension, mime_type
