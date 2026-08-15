"""
test_match_resolver.py

1. Shared helpers
2. Unit tests -- buffering, clamping
3. Unit tests -- boundary snapping (one hop only)
4. Unit tests -- minimum-duration expansion / whole-file fallback
5. Unit tests -- maximum-duration symmetric trim, matched interval preserved
6. Unit tests -- deterministic output
7. Unit tests -- invalid input handling

_get_previous_segment/_get_next_segment are patched directly in most
tests (mocker.patch.object, the project's existing convention) rather than
built from a real queryable DB -- this module's own responsibility is the
math given a neighbor (or none), not the SQL that finds one. A couple of
tests assert those two functions are each called at most once per resolve
call, which is what "one hop only, never recursive" means in practice.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility
from app.models.search_result import SearchResult
from app.models.transcript_segment import TranscriptSegment
from app.models.video import Video
from app.services import match_resolver


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

def _make_video(**overrides) -> Video:
    defaults = dict(
        id=1,
        owner_id=1,
        title="Test video",
        original_filename="test.mp4",
        file_path="videos/1/test.mp4",
        file_size_bytes=1024,
        mime_type="video/mp4",
        duration_seconds=600.0,
        status=MediaStatus.READY,
        source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    return Video(**defaults)


def _make_result(video: Video, **overrides) -> SearchResult:
    defaults = dict(
        id=1,
        query_id=1,
        video_id=video.id,
        transcript_segment_id=50,
        matched_start_time=100.0,
        matched_end_time=110.0,
        matched_text="binary search tree",
        confidence_score=0.9,
        rank_position=1,
    )
    defaults.update(overrides)
    result = SearchResult(**defaults)
    result.video = video
    return result


def _make_segment(**overrides) -> TranscriptSegment:
    defaults = dict(id=1, video_id=1, start_time=0.0, end_time=1.0, text="x")
    defaults.update(overrides)
    return TranscriptSegment(**defaults)


# Duck-typed settings -- only the attributes resolve_clip_boundaries
# actually reads. Fixed, known values so test expectations don't depend on
# real .env-tunable defaults.
def _make_settings(**overrides) -> SimpleNamespace:
    defaults = dict(
        clip_pre_buffer_seconds=3.0,
        clip_post_buffer_seconds=3.0,
        clip_min_duration_seconds=5.0,
        clip_max_duration_seconds=120.0,
        clip_max_merge_gap_seconds=1.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _patch_settings(mocker, **overrides):
    mocker.patch.object(match_resolver, "get_settings", return_value=_make_settings(**overrides))


def _patch_neighbors(mocker, prev=None, next_=None):
    prev_mock = mocker.patch.object(match_resolver, "_get_previous_segment", return_value=prev)
    next_mock = mocker.patch.object(match_resolver, "_get_next_segment", return_value=next_)
    return prev_mock, next_mock


# ===========================================================================
# 2. Buffering, clamping
# ===========================================================================

def test_pre_and_post_buffer_applied_with_no_neighbors(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=110.0)
    _patch_settings(mocker)
    _patch_neighbors(mocker, prev=None, next_=None)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time == pytest.approx(97.0)
    assert instruction.end_time == pytest.approx(113.0)


def test_clamp_start_to_zero(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=1.0, matched_end_time=10.0)
    _patch_settings(mocker, clip_pre_buffer_seconds=5.0)
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time == 0.0


def test_clamp_end_to_media_duration(mocker):
    video = _make_video(duration_seconds=100.0)
    result = _make_result(video, matched_start_time=90.0, matched_end_time=98.0)
    _patch_settings(mocker, clip_post_buffer_seconds=5.0)
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.end_time == 100.0


# ===========================================================================
# 3. Boundary snapping (one hop only)
# ===========================================================================

def test_snap_start_within_tolerance_extends_to_neighbor_start(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=110.0)
    # buffered raw_start = 97.0; neighbor ends at 97.5 -> within 1.0s tolerance
    prev_segment = _make_segment(id=49, start_time=90.0, end_time=97.5)
    _patch_settings(mocker, clip_max_merge_gap_seconds=1.0)
    prev_mock, next_mock = _patch_neighbors(mocker, prev=prev_segment, next_=None)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time == pytest.approx(90.0)
    prev_mock.assert_called_once()


def test_snap_end_within_tolerance_extends_to_neighbor_end(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=110.0)
    # buffered raw_end = 113.0; neighbor starts at 113.4 -> within 1.0s tolerance
    next_segment = _make_segment(id=51, start_time=113.4, end_time=120.0)
    _patch_settings(mocker, clip_max_merge_gap_seconds=1.0)
    prev_mock, next_mock = _patch_neighbors(mocker, prev=None, next_=next_segment)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.end_time == pytest.approx(120.0)
    next_mock.assert_called_once()


def test_snap_does_not_apply_outside_tolerance(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=110.0)
    # buffered raw_start = 97.0; neighbor ends at 80.0 -- far outside tolerance
    prev_segment = _make_segment(id=49, start_time=70.0, end_time=80.0)
    _patch_settings(mocker, clip_max_merge_gap_seconds=1.0)
    _patch_neighbors(mocker, prev=prev_segment, next_=None)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time == pytest.approx(97.0)


def test_snapping_is_single_hop_not_recursive(mocker):
    # Even if a neighbor exists, resolve_clip_boundaries must only ever
    # look up one previous and one next segment -- never chase further.
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=110.0)
    prev_segment = _make_segment(id=49, start_time=90.0, end_time=97.5)
    next_segment = _make_segment(id=51, start_time=113.4, end_time=120.0)
    _patch_settings(mocker)
    prev_mock, next_mock = _patch_neighbors(mocker, prev=prev_segment, next_=next_segment)

    match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    prev_mock.assert_called_once()
    next_mock.assert_called_once()


# ===========================================================================
# 4. Minimum-duration expansion / whole-file fallback
# ===========================================================================

def test_minimum_duration_expansion_centers_on_match(mocker):
    video = _make_video(duration_seconds=600.0)
    # matched interval itself is 1s; buffers are tiny; min duration forces expansion
    result = _make_result(video, matched_start_time=100.0, matched_end_time=101.0)
    _patch_settings(
        mocker,
        clip_pre_buffer_seconds=0.0,
        clip_post_buffer_seconds=0.0,
        clip_min_duration_seconds=10.0,
        clip_max_duration_seconds=120.0,
    )
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.duration == pytest.approx(10.0)
    match_center = 100.5
    assert instruction.start_time == pytest.approx(match_center - 5.0)
    assert instruction.end_time == pytest.approx(match_center + 5.0)


def test_minimum_duration_expansion_compensates_near_video_start(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=1.0, matched_end_time=2.0)
    _patch_settings(
        mocker,
        clip_pre_buffer_seconds=0.0,
        clip_post_buffer_seconds=0.0,
        clip_min_duration_seconds=10.0,
    )
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time == 0.0
    assert instruction.duration == pytest.approx(10.0)
    # matched interval [1, 2] must still be inside the output
    assert instruction.start_time <= 1.0
    assert instruction.end_time >= 2.0


def test_whole_file_returned_when_media_shorter_than_minimum(mocker):
    video = _make_video(duration_seconds=4.0)
    result = _make_result(video, matched_start_time=1.0, matched_end_time=2.0)
    _patch_settings(mocker, clip_min_duration_seconds=5.0)
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time == 0.0
    assert instruction.end_time == 4.0


# ===========================================================================
# 5. Maximum-duration symmetric trim
# ===========================================================================

def test_maximum_duration_trim_is_symmetric_around_match_center(mocker):
    video = _make_video(duration_seconds=1000.0)
    result = _make_result(video, matched_start_time=500.0, matched_end_time=510.0)
    _patch_settings(
        mocker,
        clip_pre_buffer_seconds=200.0,
        clip_post_buffer_seconds=200.0,
        clip_max_duration_seconds=100.0,
    )
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    match_center = 505.0
    assert instruction.duration == pytest.approx(100.0)
    assert instruction.start_time == pytest.approx(match_center - 50.0)
    assert instruction.end_time == pytest.approx(match_center + 50.0)


def test_maximum_duration_trim_preserves_matched_interval(mocker):
    video = _make_video(duration_seconds=1000.0)
    result = _make_result(video, matched_start_time=500.0, matched_end_time=510.0)
    _patch_settings(
        mocker,
        clip_pre_buffer_seconds=200.0,
        clip_post_buffer_seconds=200.0,
        clip_max_duration_seconds=100.0,
    )
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.start_time <= 500.0
    assert instruction.end_time >= 510.0


def test_maximum_duration_trim_compensates_near_video_end(mocker):
    video = _make_video(duration_seconds=520.0)
    result = _make_result(video, matched_start_time=505.0, matched_end_time=515.0)
    _patch_settings(
        mocker,
        clip_pre_buffer_seconds=200.0,
        clip_post_buffer_seconds=200.0,
        clip_max_duration_seconds=100.0,
    )
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.end_time == 520.0
    assert instruction.start_time <= 505.0
    assert instruction.end_time >= 515.0


# ===========================================================================
# 6. Deterministic output
# ===========================================================================

def test_repeated_resolution_is_deterministic(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=110.0)
    _patch_settings(mocker)
    _patch_neighbors(mocker)

    first = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)
    second = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert first.start_time == second.start_time
    assert first.end_time == second.end_time
    assert first.is_audio_only == second.is_audio_only


# ===========================================================================
# 7. Invalid input handling
# ===========================================================================

def test_null_matched_start_time_raises(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=None, matched_end_time=110.0)
    _patch_settings(mocker)

    with pytest.raises(match_resolver.InvalidTimestampsError):
        match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)


def test_null_matched_end_time_raises(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=100.0, matched_end_time=None)
    _patch_settings(mocker)

    with pytest.raises(match_resolver.InvalidTimestampsError):
        match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)


def test_reversed_timestamps_raise(mocker):
    video = _make_video(duration_seconds=600.0)
    result = _make_result(video, matched_start_time=110.0, matched_end_time=100.0)
    _patch_settings(mocker)

    with pytest.raises(match_resolver.InvalidTimestampsError):
        match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)


def test_missing_video_duration_raises(mocker):
    video = _make_video(duration_seconds=None)
    result = _make_result(video)
    _patch_settings(mocker)

    with pytest.raises(match_resolver.MissingDurationError):
        match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)


def test_zero_video_duration_raises(mocker):
    video = _make_video(duration_seconds=0.0)
    result = _make_result(video)
    _patch_settings(mocker)

    with pytest.raises(match_resolver.MissingDurationError):
        match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)


def test_is_audio_only_true_for_audio_mime_type(mocker):
    video = _make_video(duration_seconds=600.0, mime_type="audio/mpeg")
    result = _make_result(video)
    _patch_settings(mocker)
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.is_audio_only is True


def test_is_audio_only_false_for_video_mime_type(mocker):
    video = _make_video(duration_seconds=600.0, mime_type="video/mp4")
    result = _make_result(video)
    _patch_settings(mocker)
    _patch_neighbors(mocker)

    instruction = match_resolver.resolve_clip_boundaries(mocker.MagicMock(), result)

    assert instruction.is_audio_only is False
