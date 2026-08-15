"""
test_saved_result_service.py

Same style as test_clip_service.py: real ORM objects, a small hand-rolled
mock Session (query(Model) -> a per-model preset .first()/.all() result,
every chain method a pass-through returning the same query mock). This
tests service-layer branching/authorization/idempotency, not real SQL --
genuine uniqueness/cascade behavior is covered separately by the
pg_session-gated integration tests at the bottom of this file (skipped
automatically if TEST_DATABASE_URL is not configured, same convention as
every other integration test in this project).

1. Shared helpers
2. Save -- authorization, clip-required rule, persistence, idempotency
3. Unsave -- removes own row, idempotent, leaves other users' rows alone
4. Save status
5. List saved scenes for a video -- authorization, ordering delegation,
   shape
6. Database integration (pg_session, real constraints/cascades)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SearchType, UserRole
from app.models.generated_clip import GeneratedClip
from app.models.saved_result import SavedResult
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.user import User
from app.models.video import Video
from app.services import saved_result_service, video_service

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
    defaults = dict(id=1, user_id=1, query_text="binary search tree", query_type=SearchType.EXACT_TEXT)
    defaults.update(overrides)
    return SearchQuery(**defaults)


def _make_result(video: Video, query: SearchQuery, clip: GeneratedClip | None = None, **overrides) -> SearchResult:
    defaults = dict(
        id=1, query_id=query.id, video_id=video.id, transcript_segment_id=50,
        matched_start_time=100.0, matched_end_time=110.0, matched_text="binary search tree",
        confidence_score=0.9, rank_position=1, selected_at=None,
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


def _make_mock_db(video=None, result=None, saved=None, saved_list=None):
    mock_db = MagicMock()
    added: list = []
    deleted: list = []
    mock_db.add.side_effect = added.append
    mock_db.delete.side_effect = deleted.append
    mock_db.commit.side_effect = lambda: None
    mock_db.rollback.side_effect = lambda: None
    mock_db.refresh.side_effect = lambda obj: None
    mock_db._added = added
    mock_db._deleted = deleted

    def _query(model):
        q = MagicMock()
        q.options.return_value = q
        q.filter.return_value = q
        q.join.return_value = q
        q.order_by.return_value = q
        if model is Video:
            q.first.return_value = video
        elif model is SearchResult:
            q.first.return_value = result
        elif model is SavedResult:
            q.first.return_value = saved
            q.all.return_value = saved_list if saved_list is not None else []
        else:
            q.first.return_value = None
            q.all.return_value = []
        return q

    mock_db.query.side_effect = _query
    return mock_db


# ===========================================================================
# 2. Save
# ===========================================================================


def test_owner_can_save_accessible_generated_result():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    clip = _make_clip(result, video)
    result.clip = clip
    db = _make_mock_db(result=result, saved=None)

    saved = saved_result_service.save_result(db, user, result.id)

    assert saved.user_id == 1
    assert saved.search_result_id == result.id
    assert saved in db._added


def test_any_authorized_user_can_save_shared_video_result():
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.SHARED)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    db = _make_mock_db(result=result, saved=None)

    saved = saved_result_service.save_result(db, other_user, result.id)

    assert saved.user_id == other_user.id


def test_duplicate_save_does_not_create_a_duplicate_row():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    existing = SavedResult(id=1, user_id=1, search_result_id=result.id)
    db = _make_mock_db(result=result, saved=existing)

    saved = saved_result_service.save_result(db, user, result.id)

    assert saved is existing
    assert len(db._added) == 0


def test_cannot_save_result_without_generated_clip():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query, clip=None)
    db = _make_mock_db(result=result, saved=None)

    with pytest.raises(saved_result_service.ClipNotGeneratedError):
        saved_result_service.save_result(db, user, result.id)

    assert len(db._added) == 0


def test_cannot_save_inaccessible_private_result():
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.PRIVATE)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    db = _make_mock_db(result=result, saved=None)

    with pytest.raises(saved_result_service.ResultNotFoundError):
        saved_result_service.save_result(db, other_user, result.id)


def test_missing_result_returns_not_found_on_save():
    user = _make_user(id=1)
    db = _make_mock_db(result=None, saved=None)

    with pytest.raises(saved_result_service.ResultNotFoundError):
        saved_result_service.save_result(db, user, 999)


def test_save_race_condition_returns_existing_row_after_integrity_error():
    # Simulates a concurrent duplicate insert -- the first .first() lookup
    # (before insert) finds nothing, commit() raises IntegrityError (unique
    # constraint), and the code must recover by re-querying rather than
    # propagating the error to the caller.
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)

    winner_row = SavedResult(id=7, user_id=1, search_result_id=result.id)
    call_count = {"n": 0}

    db = _make_mock_db(result=result, saved=None)

    def _query_side_effect(model):
        q = MagicMock()
        q.options.return_value = q
        q.filter.return_value = q
        if model is SearchResult:
            q.first.return_value = result
            return q
        if model is SavedResult:
            call_count["n"] += 1
            # First lookup (pre-insert): nothing yet. Second lookup (after
            # the simulated race/rollback): the concurrent winner's row.
            q.first.return_value = None if call_count["n"] == 1 else winner_row
            return q
        q.first.return_value = None
        return q

    db.query.side_effect = _query_side_effect
    db.commit.side_effect = IntegrityError("duplicate key", params=None, orig=Exception("dup"))

    saved = saved_result_service.save_result(db, user, result.id)

    assert saved is winner_row
    db.rollback.assert_called_once()


# ===========================================================================
# 3. Unsave
# ===========================================================================


def test_unsave_removes_current_users_saved_row():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    existing = SavedResult(id=1, user_id=1, search_result_id=result.id)
    db = _make_mock_db(result=result, saved=existing)

    saved_result_service.unsave_result(db, user, result.id)

    assert existing in db._deleted


def test_unsave_is_idempotent_when_nothing_is_saved():
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    db = _make_mock_db(result=result, saved=None)

    # Must not raise, and must not attempt a delete.
    saved_result_service.unsave_result(db, user, result.id)

    assert len(db._deleted) == 0


def test_unsave_does_not_touch_another_users_row():
    # The service's own SavedResult query is filtered on
    # (user_id=caller, search_result_id=...) -- from this caller's
    # perspective, another user's saved row simply doesn't show up in that
    # lookup, so `existing` here correctly comes back None and nothing is
    # deleted, exactly like the "nothing saved" case above.
    user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=1, visibility=MediaVisibility.SHARED)
    query = _make_query()
    result = _make_result(video, query)
    result.clip = _make_clip(result, video)
    db = _make_mock_db(result=result, saved=None)

    saved_result_service.unsave_result(db, user, result.id)

    assert len(db._deleted) == 0


def test_unsave_missing_result_returns_not_found():
    user = _make_user(id=1)
    db = _make_mock_db(result=None, saved=None)

    with pytest.raises(saved_result_service.ResultNotFoundError):
        saved_result_service.unsave_result(db, user, 999)


# ===========================================================================
# 4. Save status
# ===========================================================================


def test_is_saved_true_when_row_exists():
    db = _make_mock_db(saved=SavedResult(id=1, user_id=1, search_result_id=5))
    assert saved_result_service.is_saved(db, 1, 5) is True


def test_is_saved_false_when_no_row():
    db = _make_mock_db(saved=None)
    assert saved_result_service.is_saved(db, 1, 5) is False


# ===========================================================================
# 5. List saved scenes for a video
# ===========================================================================


def test_list_saved_for_video_requires_video_access(mocker):
    user = _make_user(id=1)
    mocker.patch.object(video_service, "get_video", side_effect=video_service.VideoNotFoundError())
    db = _make_mock_db()

    with pytest.raises(video_service.VideoNotFoundError):
        saved_result_service.list_saved_for_video(db, user, 999)


def test_list_saved_for_video_returns_scenes_for_owned_video(mocker):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    clip = _make_clip(result, video)
    result.clip = clip
    result.query = query
    saved_row = SavedResult(id=1, user_id=1, search_result_id=result.id)
    saved_row.result = result

    mocker.patch.object(video_service, "get_video", return_value=video)
    db = _make_mock_db(saved_list=[saved_row])

    scenes = saved_result_service.list_saved_for_video(db, user, video.id)

    assert len(scenes) == 1
    assert scenes[0].saved_result is saved_row
    assert scenes[0].clip is clip
    assert scenes[0].video is video


def test_list_saved_for_video_empty_list(mocker):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    mocker.patch.object(video_service, "get_video", return_value=video)
    db = _make_mock_db(saved_list=[])

    scenes = saved_result_service.list_saved_for_video(db, user, video.id)

    assert scenes == []


# ===========================================================================
# 6. Database integration (real Postgres, gated by TEST_DATABASE_URL)
# ===========================================================================


class TestDatabaseIntegration:
    """Real-Postgres tests -- skipped automatically (via pg_session's own
    skip) if TEST_DATABASE_URL is not configured. Covers exactly the shape
    the mocked unit tests above cannot: the actual unique constraint and
    actual ON DELETE CASCADE behavior."""

    def _seed_user(self, pg_session, **overrides):
        defaults = dict(
            full_name="Test User", username=f"user{id(overrides)}", email=f"user{id(overrides)}@example.com",
            password_hash="hash", role=UserRole.USER,
        )
        defaults.update(overrides)
        user = User(**defaults)
        pg_session.add(user)
        pg_session.flush()
        return user

    def _seed_chain(self, pg_session, user):
        video = Video(
            owner_id=user.id, title="Integration video", original_filename="int.mp4",
            file_path="videos/x/int.mp4", file_size_bytes=10, mime_type="video/mp4",
            status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
            visibility=MediaVisibility.PRIVATE,
        )
        pg_session.add(video)
        pg_session.flush()

        query = SearchQuery(user_id=user.id, query_text="test", query_type=SearchType.EXACT_TEXT)
        pg_session.add(query)
        pg_session.flush()

        result = SearchResult(
            query_id=query.id, video_id=video.id, matched_start_time=0.0, matched_end_time=5.0,
            confidence_score=0.9, rank_position=1,
        )
        pg_session.add(result)
        pg_session.flush()

        clip = GeneratedClip(
            result_id=result.id, video_id=video.id, start_time=0.0, end_time=5.0,
            clip_path="clips/x/int.mp4", clip_url="/api/clips/1",
        )
        pg_session.add(clip)
        pg_session.flush()
        return video, query, result, clip

    def test_unique_constraint_prevents_duplicate_saved_row(self, pg_session):
        user = self._seed_user(pg_session, username="uniqtest", email="uniqtest@example.com")
        _video, _query, result, _clip = self._seed_chain(pg_session, user)

        pg_session.add(SavedResult(user_id=user.id, search_result_id=result.id))
        pg_session.flush()

        pg_session.add(SavedResult(user_id=user.id, search_result_id=result.id))
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_deleting_search_result_cascades_to_saved_results(self, pg_session):
        user = self._seed_user(pg_session, username="cascadetest1", email="cascadetest1@example.com")
        _video, _query, result, _clip = self._seed_chain(pg_session, user)
        saved = SavedResult(user_id=user.id, search_result_id=result.id)
        pg_session.add(saved)
        pg_session.flush()
        saved_id = saved.id

        pg_session.delete(result)
        pg_session.flush()

        assert pg_session.get(SavedResult, saved_id) is None

    def test_deleting_user_cascades_to_saved_results(self, pg_session):
        user = self._seed_user(pg_session, username="cascadetest2", email="cascadetest2@example.com")
        _video, _query, result, _clip = self._seed_chain(pg_session, user)
        saved = SavedResult(user_id=user.id, search_result_id=result.id)
        pg_session.add(saved)
        pg_session.flush()
        saved_id = saved.id

        pg_session.delete(user)
        pg_session.flush()

        assert pg_session.get(SavedResult, saved_id) is None
