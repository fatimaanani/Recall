"""
test_subtitle_parser.py

Unit tests for app/processing/subtitle_parser.py -- SRT/VTT text parsing
into transcript_segmenter.RawCue objects.

1. SRT parsing
2. VTT parsing
3. Multi-line cues (joined with a single space)
4. Blank cues dropped
5. VTT cue-settings lines discarded, not misread as text
6. Malformed / empty input
7. parse_subtitle_file dispatch
"""

from __future__ import annotations

import pytest

from app.processing.subtitle_parser import SubtitleParseError, parse_srt, parse_subtitle_file, parse_vtt


# ===========================================================================
# 1. SRT parsing
# ===========================================================================

def test_parses_basic_srt():
    srt = (
        "1\n00:00:00,000 --> 00:00:02,500\nHello there.\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\nSecond cue.\n"
    )
    cues = parse_srt(srt)
    assert len(cues) == 2
    assert cues[0].start == 0.0
    assert cues[0].end == 2.5
    assert cues[0].text == "Hello there."
    assert cues[1].start == 3.0
    assert cues[1].text == "Second cue."


def test_srt_timestamps_with_hours_are_parsed_correctly():
    srt = "1\n01:02:03,500 --> 01:02:05,000\nLater cue.\n"
    cues = parse_srt(srt)
    assert cues[0].start == pytest.approx(3723.5)
    assert cues[0].end == pytest.approx(3725.0)


# ===========================================================================
# 2. VTT parsing
# ===========================================================================

def test_parses_basic_vtt():
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.500\nHello there.\n\n00:00:03.000 --> 00:00:05.000\nSecond cue.\n"
    cues = parse_vtt(vtt)
    assert len(cues) == 2
    assert cues[0].text == "Hello there."
    assert cues[1].start == 3.0


def test_vtt_with_cue_identifiers_still_parses():
    # VTT cues can have an optional identifier line before the timestamp,
    # same structural role as SRT's numeric index.
    vtt = "WEBVTT\n\ncue-1\n00:00:00.000 --> 00:00:02.000\nHello.\n"
    cues = parse_vtt(vtt)
    assert len(cues) == 1
    assert cues[0].text == "Hello."


# ===========================================================================
# 3. Multi-line cues
# ===========================================================================

def test_multi_line_cue_text_is_joined_with_a_single_space():
    srt = "1\n00:00:00,000 --> 00:00:02,000\nFirst line\nsecond line\n"
    cues = parse_srt(srt)
    assert cues[0].text == "First line second line"


# ===========================================================================
# 4. Blank cues dropped
# ===========================================================================

def test_blank_cue_is_dropped_not_kept_as_empty_text():
    srt = "1\n00:00:00,000 --> 00:00:02,000\n\n\n2\n00:00:03,000 --> 00:00:05,000\nReal text.\n"
    cues = parse_srt(srt)
    assert len(cues) == 1
    assert cues[0].text == "Real text."


# ===========================================================================
# 5. VTT cue-settings lines discarded
# ===========================================================================

def test_vtt_cue_settings_are_not_treated_as_text():
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000 position:10%,line-0 align:start\nActual caption text.\n"
    cues = parse_vtt(vtt)
    assert len(cues) == 1
    assert cues[0].text == "Actual caption text."
    assert "position" not in cues[0].text
    assert "align" not in cues[0].text


# ===========================================================================
# 6. Malformed / empty input
# ===========================================================================

def test_parse_srt_with_no_cues_returns_empty_list():
    assert parse_srt("this has no timestamps at all") == []


def test_parse_vtt_header_only_returns_empty_list():
    assert parse_vtt("WEBVTT\n\n") == []


def test_parse_subtitle_file_raises_on_empty_result():
    with pytest.raises(SubtitleParseError):
        parse_subtitle_file("srt", "no cues here")


# ===========================================================================
# 7. parse_subtitle_file dispatch
# ===========================================================================

def test_parse_subtitle_file_dispatches_to_srt():
    cues = parse_subtitle_file("srt", "1\n00:00:00,000 --> 00:00:01,000\nHi.\n")
    assert len(cues) == 1


def test_parse_subtitle_file_dispatches_to_vtt():
    cues = parse_subtitle_file("vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHi.\n")
    assert len(cues) == 1


def test_parse_subtitle_file_rejects_unknown_extension():
    with pytest.raises(SubtitleParseError):
        parse_subtitle_file("txt", "irrelevant")
