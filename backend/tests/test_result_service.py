"""
test_result_service.py

Same mocked-db unit-test style as test_clip_service.py /
test_saved_result_service.py.

1. Shared helpers
2. Authorization (owner, shared, another user's private, missing)
3. Field mapping (query_text resolution, clip presence, categories)
4. Saved status is current-user-specific
5. Summary / Key Points delegation to transcript_summary_service
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SearchScope, SearchType, UserRole
from app.models.category import Category
from app.models.generated_clip import GeneratedClip
from app.models.saved_result import SavedResult
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.user import User
from app.models.video import Video
from app.models.video_category import VideoCategory
from app.services import result_service

# ===========================================================================
# 1. Shared helpers
# ===========================================================================


def _make_user(**overrides) -> User:
    defaults = dict(
        id=1, full_name="Test User", username="testuser", email="test@example.com",
        password_hash="not-a-real-hash", role=UserRole.USER,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_video(**overrides) -> Video:
    defaults = dict(
        id=1, owner_id=1, title="Test video", original_filename="test.mp4",
        file_path="videos/1/source.mp4", file_size_bytes=1024, mime_type="video/mp4",
        duration_seconds=600.0, status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    video = Video(**defaults)
    video.category_links = []
    return video


def _make_query(**overrides) -> SearchQuery:
    defaults = dict(
        id=1, user_id=1, query_text="binary search tree", query_type=SearchType.EXACT_TEXT,
        search_scope=SearchScope.BOTH,
    )
    defaults.update(overrides)
    return SearchQuery(**defaults)


def _make_result(video: Video, query: SearchQuery, clip=None, **overrides) -> SearchResult:
    defaults = dict(
        id=1, query_id=query.id, video_id=video.id, transcript_segment_id=50,
        matched_start_time=100.0, matched_end_time=110.0, matched_text="binary search tree",
        confidence_score=0.9, keyword_score=0.8, semantic_score=0.7, rank_position=1, selected_at=None,
    )
    defaults.update(overrides)
    result = SearchResult(**defaults)
    result.video = video
    result.query = query
    result.clip = clip
    return result


def _make_clip(result: SearchResult, video: Video, **overrides) -> GeneratedClip:
    defaults = dict(
        id=1, result_id=result.id, video_id=video.id, start_time=97.0, end_time=113.0,
        clip_path=f"clips/{video.id}/existing.mp4", clip_url="/api/clips/1",
    )
    defaults.update(overrides)
    return GeneratedClip(**defaults)


def _make_mock_db(result=None, saved=None):
    mock_db = MagicMock()

    def _query(model):
        q = MagicMock()
        q.options.return_value = q
        q.filter.return_value = q
        if model is SearchResult:
            q.first.return_value = result
        elif model is SavedResult:
            q.first.return_value = saved
        else:
            q.first.return_value = None
        return q

    mock_db.query.side_effect = _query
    return mock_db


# ===========================================================================
# 2. Authorization
# ===========================================================================


def test_owner_can_fetch_own_result():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, visibility=MediaVisibility.PRIVATE)
    query = _make_query()
    result = _make_result(video, query)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.result_id == result.id
    assert detail.video_id == video.id


def test_any_authorized_user_can_fetch_shared_video_result():
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.SHARED)
    query = _make_query()
    result = _make_result(video, query)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, other_user, result.id)

    assert detail.result_id == result.id


def test_another_users_private_result_returns_not_found():
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.PRIVATE)
    query = _make_query()
    result = _make_result(video, query)
    db = _make_mock_db(result=result)

    with pytest.raises(result_service.ResultNotFoundError):
        result_service.get_result_detail(db, other_user, result.id)


def test_missing_result_returns_not_found():
    user = _make_user(id=1)
    db = _make_mock_db(result=None)

    with pytest.raises(result_service.ResultNotFoundError):
        result_service.get_result_detail(db, user, 999)


# ===========================================================================
# 3. Field mapping
# ===========================================================================


def test_typed_query_uses_query_text():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query(query_type=SearchType.EXACT_TEXT, query_text="hello world", transcribed_text=None)
    result = _make_result(video, query)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.query_text == "hello world"
    assert detail.query_type == SearchType.EXACT_TEXT


def test_speech_to_text_query_uses_transcribed_text():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query(
        query_type=SearchType.SPEECH_TO_TEXT, query_text=None, transcribed_text="what i said out loud",
    )
    result = _make_result(video, query)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.query_text == "what i said out loud"


def test_clip_present_populates_clip_summary():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="video/mp4")
    query = _make_query()
    result = _make_result(video, query)
    clip = _make_clip(result, video, start_time=10.0, end_time=25.0)
    result.clip = clip
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.clip is not None
    assert detail.clip.generated_clip_id == clip.id
    assert detail.clip.duration == 15.0
    assert detail.clip.clip_stream_url == "/api/clips/1"
    assert detail.clip.is_audio_only is False


def test_no_clip_yet_leaves_clip_none():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query, clip=None)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.clip is None


def test_audio_video_reports_is_audio_only():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="audio/mpeg")
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.media_type == "audio"
    assert detail.clip.is_audio_only is True


def test_categories_mapped_from_video_category_links():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)

    # Video.category_links is a real SQLAlchemy-instrumented relationship
    # (Mapped[list["VideoCategory"]]). Assigning it a list of plain,
    # non-mapped objects fails at assignment time because the
    # InstrumentedList validates that every appended item is a mapped
    # instance carrying `_sa_instance_state` -- plain classes don't have
    # that attribute. The fix is to build the relationship out of real
    # mapped VideoCategory/Category instances instead of fakes; because
    # these are just constructed in memory (never added to a Session),
    # this stays a pure unit test with no database/fixture dependency,
    # consistent with every other test in this file and in
    # test_saved_result_service.py.
    video.category_links = [
        VideoCategory(video_id=video.id, category_id=1, category=Category(id=1, name="Lecture")),
        VideoCategory(video_id=video.id, category_id=2, category=Category(id=2, name="Week 5")),
    ]
    query = _make_query()
    result = _make_result(video, query)
    db = _make_mock_db(result=result)

    detail = result_service.get_result_detail(db, user, result.id)

    assert [c.name for c in detail.categories] == ["Lecture", "Week 5"]


# ===========================================================================
# 4. Saved status is current-user-specific
# ===========================================================================


def test_is_saved_true_for_this_user(mocker):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    db = _make_mock_db(result=result)
    mocker.patch("app.services.result_service.saved_result_service.is_saved", return_value=True)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.is_saved is True


def test_is_saved_false_when_not_saved(mocker):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    db = _make_mock_db(result=result)
    mocker.patch("app.services.result_service.saved_result_service.is_saved", return_value=False)

    detail = result_service.get_result_detail(db, user, result.id)

    assert detail.is_saved is False


# ===========================================================================
# 5. Summary / Key Points delegation (real algorithm covered separately in
#    test_transcript_summary_service.py -- these tests only confirm
#    result_service wires it correctly: called with the clip's window, not
#    matched_start_time/matched_end_time, and skipped entirely with no clip)
# ===========================================================================


def test_summary_and_key_points_populated_when_clip_present(mocker):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    clip = _make_clip(result, video, start_time=10.0, end_time=25.0)
    result.clip = clip
    db = _make_mock_db(result=result)

    fake_segments = ["segment-a", "segment-b"]
    select_mock = mocker.patch(
        "app.services.result_service.transcript_summary_service.select_overlapping_segments",
        return_value=fake_segments,
    )
    mocker.patch(
        "app.services.result_service.transcript_summary_service.build_scene_summary",
        return_value=("full span text", "a short summary", ["point one", "point two"]),
    )

    detail = result_service.get_result_detail(db, user, result.id)

    # Called with the clip's own boundaries, not the result's
    # matched_start_time/matched_end_time (the clip window, per the
    # approved scope, is what gets summarized -- not the raw match).
    select_mock.assert_called_once_with(db, video.id, clip.start_time, clip.end_time)
    assert detail.transcript_span_text == "full span text"
    assert detail.summary == "a short summary"
    assert detail.key_points == ["point one", "point two"]


def test_summary_and_key_points_none_when_no_clip(mocker):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query, clip=None)
    db = _make_mock_db(result=result)

    select_mock = mocker.patch(
        "app.services.result_service.transcript_summary_service.select_overlapping_segments"
    )

    detail = result_service.get_result_detail(db, user, result.id)

    select_mock.assert_not_called()
    assert detail.transcript_span_text is None
    assert detail.summary is None
    assert detail.key_points == []


def test_enrichment_appears_on_a_second_call_after_clip_generation_without_any_write(mocker):
    # Models a real frontend sequencing case: Scene Viewer's first
    # GET /api/results/{id} can genuinely run before a
    # not-yet-cached result's clip exists (honestly summary=None at that
    # point), and the fix is a second GET after clip generation succeeds --
    # never a clip regeneration. This proves both halves of that contract
    # at the service layer: (1) the same SearchResult row transitions from
    # no-summary to real-summary purely because `clip` is now attached, and
    # (2) get_result_detail itself never writes anything -- no db.add,
    # db.flush, or db.commit call, on either the pre- or post-clip call --
    # so an "enrichment refresh" can never create a second GeneratedClip
    # row or any other row.
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query, clip=None)
    db = _make_mock_db(result=result)

    mocker.patch(
        "app.services.result_service.transcript_summary_service.select_overlapping_segments",
        return_value=["segment-a"],
    )
    mocker.patch(
        "app.services.result_service.transcript_summary_service.build_scene_summary",
        return_value=("full span text", "a real summary", ["point one"]),
    )

    # 1. Before clip generation -- honest empty state, not fabricated.
    before = result_service.get_result_detail(db, user, result.id)
    assert before.summary is None
    assert before.key_points == []

    # 2. Clip generation succeeds elsewhere (clip_service.get_or_create_clip,
    # covered in test_clip_service.py) -- simulated here by attaching the
    # clip to the same result row, exactly like a real second GET would
    # see it after a real POST /api/results/{id}/clip commits.
    clip = _make_clip(result, video, start_time=10.0, end_time=25.0)
    result.clip = clip

    # 3. The enrichment re-fetch -- same function, same result id, no
    # regeneration.
    after = result_service.get_result_detail(db, user, result.id)
    assert after.summary == "a real summary"
    assert after.key_points == ["point one"]

    # Read-only across both calls -- no row was ever created or modified
    # by get_result_detail itself.
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()
