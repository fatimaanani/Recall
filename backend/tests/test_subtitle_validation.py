"""
test_subtitle_validation.py

Unit tests for app/utils/subtitle_validation.py -- upload-time validation
for an optional SRT/VTT subtitle file, mirroring file_validation.py's
role for video/audio uploads.

1. Extension allowlist
2. Empty / oversized rejection
3. Encoding rejection
4. SRT structural validation
5. VTT structural validation
"""

from __future__ import annotations

import pytest

from app.utils.subtitle_validation import InvalidSubtitleFileError, validate_subtitle_upload

_VALID_SRT = b"""1
00:00:00,000 --> 00:00:02,500
Hello there.
"""

_VALID_VTT = b"""WEBVTT

00:00:00.000 --> 00:00:02.500
Hello there.
"""

_MAX_SIZE = 2 * 1024 * 1024


# ===========================================================================
# 1. Extension allowlist
# ===========================================================================

def test_srt_extension_is_accepted():
    extension = validate_subtitle_upload("captions.srt", _VALID_SRT, _MAX_SIZE)
    assert extension == "srt"


def test_vtt_extension_is_accepted():
    extension = validate_subtitle_upload("captions.vtt", _VALID_VTT, _MAX_SIZE)
    assert extension == "vtt"


def test_unsupported_extension_is_rejected():
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.txt", _VALID_SRT, _MAX_SIZE)


def test_no_extension_is_rejected():
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions", _VALID_SRT, _MAX_SIZE)


def test_video_extension_disguised_as_subtitle_name_is_rejected():
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.mp4", _VALID_SRT, _MAX_SIZE)


# ===========================================================================
# 2. Empty / oversized rejection
# ===========================================================================

def test_empty_file_is_rejected():
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.srt", b"", _MAX_SIZE)


def test_oversized_file_is_rejected():
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.srt", _VALID_SRT, max_size_bytes=5)


# ===========================================================================
# 3. Encoding rejection
# ===========================================================================

def test_non_utf8_content_is_rejected():
    invalid_bytes = b"\xff\xfe\x00\x81not valid utf-8"
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.srt", invalid_bytes, _MAX_SIZE)


def test_utf8_bom_is_accepted():
    bom_prefixed = b"\xef\xbb\xbf" + _VALID_SRT
    extension = validate_subtitle_upload("captions.srt", bom_prefixed, _MAX_SIZE)
    assert extension == "srt"


# ===========================================================================
# 4. SRT structural validation
# ===========================================================================

def test_srt_without_a_timestamp_line_is_rejected():
    bogus = b"This is just plain text, not a real subtitle file at all."
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.srt", bogus, _MAX_SIZE)


def test_srt_with_vtt_style_timestamp_is_rejected():
    # Period instead of comma before milliseconds -- a VTT timestamp
    # given the wrong extension, must not be accepted as SRT.
    wrong_style = b"00:00:00.000 --> 00:00:02.500\nHello."
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.srt", wrong_style, _MAX_SIZE)


# ===========================================================================
# 5. VTT structural validation
# ===========================================================================

def test_vtt_without_webvtt_header_is_rejected():
    missing_header = b"00:00:00.000 --> 00:00:02.500\nHello there.\n"
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.vtt", missing_header, _MAX_SIZE)


def test_vtt_with_srt_style_timestamp_is_rejected():
    # Comma instead of period -- an SRT timestamp given the wrong
    # extension, must not be accepted as VTT even with a WEBVTT header.
    wrong_style = b"WEBVTT\n\n00:00:00,000 --> 00:00:02,500\nHello.\n"
    with pytest.raises(InvalidSubtitleFileError):
        validate_subtitle_upload("captions.vtt", wrong_style, _MAX_SIZE)
