"""
test_subtitle_extraction.py

Unit tests for two app/processing/ffmpeg_processor.py functions:
probe_embedded_subtitle_stream_index (ffprobe) and
extract_embedded_subtitle (ffmpeg). Mocked subprocess.run, real
filesystem via tmp_path -- same convention as test_clip_service.py's
section 10 (ffmpeg_processor.generate_clip tests).

1. probe_embedded_subtitle_stream_index
2. extract_embedded_subtitle
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from app.processing import ffmpeg_processor
from app.processing.ffmpeg_processor import ProcessingError

_FAKE_SETTINGS = SimpleNamespace(
    ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe", ffmpeg_timeout_seconds=5,
)


# ===========================================================================
# 1. probe_embedded_subtitle_stream_index
# ===========================================================================

def test_probe_returns_index_of_first_extractable_subtitle_stream(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    stdout = json.dumps({"streams": [{"index": 3, "codec_name": "subrip"}]})
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
    )

    result = ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mkv")
    assert result == 3


def test_probe_picks_first_match_when_multiple_subtitle_streams_exist(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    stdout = json.dumps({
        "streams": [
            {"index": 2, "codec_name": "subrip"},
            {"index": 5, "codec_name": "ass"},
        ]
    })
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
    )

    result = ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mkv")
    assert result == 2


def test_probe_returns_none_when_no_subtitle_streams_exist(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    stdout = json.dumps({"streams": []})
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
    )

    assert ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mp4") is None


def test_probe_returns_none_when_streams_have_unextractable_codecs(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    # e.g. a bitmap-based subtitle codec (dvd_subtitle/hdmv_pgs_subtitle) --
    # present, but not one this pipeline can turn into text.
    stdout = json.dumps({"streams": [{"index": 4, "codec_name": "dvd_subtitle"}]})
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
    )

    assert ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mkv") is None


def test_probe_returns_none_on_ffprobe_failure_never_raises(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        side_effect=subprocess.CalledProcessError(1, "ffprobe", stderr="not a valid container"),
    )

    # Must not raise -- probing is a best-effort bonus signal, never fatal.
    assert ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mp4") is None


def test_probe_returns_none_on_missing_binary(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=FileNotFoundError())

    assert ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mp4") is None


def test_probe_returns_none_on_malformed_json(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 0, stdout="not json", stderr=""),
    )

    assert ffmpeg_processor.probe_embedded_subtitle_stream_index(tmp_path / "in.mp4") is None


# ===========================================================================
# 2. extract_embedded_subtitle
# ===========================================================================

def test_extract_writes_the_destination_file(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    dest = tmp_path / "out.srt"

    def _fake_run(command, **kwargs):
        dest.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi.\n")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=_fake_run)

    ffmpeg_processor.extract_embedded_subtitle(tmp_path / "in.mkv", dest, stream_index=2)

    assert dest.exists()
    assert dest.read_text().startswith("1\n")


def test_extract_uses_stream_map_and_srt_codec(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    dest = tmp_path / "out.srt"
    captured = {}

    def _fake_run(command, **kwargs):
        captured["command"] = command
        dest.write_text("content")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=_fake_run)

    ffmpeg_processor.extract_embedded_subtitle(tmp_path / "in.mkv", dest, stream_index=3)

    assert "0:3" in captured["command"]
    assert "srt" in captured["command"]


def test_extract_raises_on_missing_binary(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=FileNotFoundError())

    with pytest.raises(ProcessingError):
        ffmpeg_processor.extract_embedded_subtitle(tmp_path / "in.mkv", tmp_path / "out.srt", 0)


def test_extract_raises_on_timeout(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=5),
    )

    with pytest.raises(ProcessingError):
        ffmpeg_processor.extract_embedded_subtitle(tmp_path / "in.mkv", tmp_path / "out.srt", 0)


def test_extract_raises_when_ffmpeg_reports_success_but_no_file_produced(mocker, tmp_path):
    mocker.patch.object(ffmpeg_processor, "settings", _FAKE_SETTINGS)
    dest = tmp_path / "out.srt"  # deliberately never written by the fake run below

    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    )

    with pytest.raises(ProcessingError):
        ffmpeg_processor.extract_embedded_subtitle(tmp_path / "in.mkv", dest, 0)
