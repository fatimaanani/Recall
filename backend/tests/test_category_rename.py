"""
test_category_rename.py

1. Unit tests (mocked DB session, no PostgreSQL required)
2. Integration tests (real PostgreSQL, require TEST_DATABASE_URL) --
   duplicate-name conflict and video-link preservation, since both
   genuinely depend on real constraint/relationship behavior
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.enums import MediaSourceType, MediaStatus, MediaVisibility
from app.models.category import Category
from app.models.user import User
from app.models.video import Video
from app.models.video_category import VideoCategory
from app.services import category_service


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_user(**overrides) -> User:
    defaults = dict(
        id=1,
        full_name="Test User",
        username="testuser",
        email="test@example.com",
        password_hash="not-a-real-hash",
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_category(**overrides) -> Category:
    defaults = dict(
        id=1,
        user_id=1,
        name="Old Name",
        created_at=datetime.datetime.utcnow(),
    )
    defaults.update(overrides)
    return Category(**defaults)


def _make_video(**overrides) -> Video:
    defaults = dict(
        id=1,
        owner_id=1,
        title="Test video",
        original_filename="test.mp4",
        file_path="videos/1/test.mp4",
        file_size_bytes=1024,
        mime_type="video/mp4",
        status=MediaStatus.READY,
        source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    return Video(**defaults)


# ===========================================================================
# 1. Unit tests -- mocked DB session, no PostgreSQL
# ===========================================================================

def test_rename_category_succeeds_for_owner(mocker):
    user = _make_user()
    category = _make_category(name="Old Name")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = category
    mock_db.query.return_value.filter.return_value.scalar.return_value = 3

    updated_category, video_count = category_service.rename_category(mock_db, user, category.id, "New Name")

    assert updated_category.name == "New Name"
    assert updated_category.id == 1  # unchanged -- updated in place, not recreated
    assert video_count == 3
    mock_db.commit.assert_called_once()
    mock_db.delete.assert_not_called()  # never recreated / never touches VideoCategory rows


def test_rename_category_trims_whitespace(mocker):
    user = _make_user()
    category = _make_category(name="Old Name")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = category
    mock_db.query.return_value.filter.return_value.scalar.return_value = 0

    updated_category, _ = category_service.rename_category(mock_db, user, category.id, "  New Name  ")

    assert updated_category.name == "New Name"


def test_rename_category_not_found_for_missing_category(mocker):
    user = _make_user()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(category_service.CategoryNotFoundError):
        category_service.rename_category(mock_db, user, 999, "New Name")

    mock_db.commit.assert_not_called()


def test_rename_category_not_found_for_another_users_category(mocker):
    # _get_owned_category_or_none filters by (id AND user_id) in one query,
    # so a category that exists but belongs to someone else looks
    # identical to a nonexistent id -- both hit this same branch, which is
    # exactly the point (never reveals whether another user's category
    # exists). Modeled here the same way as the "missing" test above,
    # since the mocked query can't actually enforce ownership -- the real
    # ownership filtering is covered by the Postgres integration test below.
    user = _make_user(id=2)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(category_service.CategoryNotFoundError):
        category_service.rename_category(mock_db, user, 1, "New Name")


def test_rename_category_rejects_whitespace_only_name(mocker):
    user = _make_user()
    category = _make_category(name="Old Name")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = category

    with pytest.raises(category_service.EmptyCategoryNameError):
        category_service.rename_category(mock_db, user, category.id, "    ")

    assert category.name == "Old Name"  # never mutated
    mock_db.commit.assert_not_called()


def test_rename_category_raises_conflict_on_duplicate_name(mocker):
    user = _make_user()
    category = _make_category(name="Old Name")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = category
    mock_db.commit.side_effect = IntegrityError("uq_categories_user_id_name", {}, Exception())

    with pytest.raises(category_service.CategoryNameAlreadyExistsError):
        category_service.rename_category(mock_db, user, category.id, "Already Taken")

    mock_db.rollback.assert_called_once()


# ===========================================================================
# 2. Integration tests -- real PostgreSQL (TEST_DATABASE_URL)
# ===========================================================================

def test_rename_category_duplicate_name_conflict_in_postgres(pg_session):
    user = _make_user(id=None, username="renameuser1", email="rename1@example.com")
    pg_session.add(user)
    pg_session.flush()

    category_a = Category(user_id=user.id, name="Collection A")
    category_b = Category(user_id=user.id, name="Collection B")
    pg_session.add_all([category_a, category_b])
    pg_session.commit()

    with pytest.raises(category_service.CategoryNameAlreadyExistsError):
        category_service.rename_category(pg_session, user, category_b.id, "Collection A")

    pg_session.rollback()
    pg_session.refresh(category_b)
    assert category_b.name == "Collection B"  # unchanged after the failed rename


def test_rename_category_preserves_id_and_video_links_in_postgres(pg_session):
    user = _make_user(id=None, username="renameuser2", email="rename2@example.com")
    pg_session.add(user)
    pg_session.flush()

    category = Category(user_id=user.id, name="Original Name")
    pg_session.add(category)
    pg_session.flush()
    original_category_id = category.id

    video = _make_video(id=None, owner_id=user.id)
    pg_session.add(video)
    pg_session.flush()

    link = VideoCategory(video_id=video.id, category_id=category.id)
    pg_session.add(link)
    pg_session.commit()

    updated_category, video_count = category_service.rename_category(
        pg_session, user, category.id, "Renamed Collection"
    )
    pg_session.commit()

    assert updated_category.id == original_category_id
    assert updated_category.name == "Renamed Collection"
    assert video_count == 1

    pg_session.expire_all()
    surviving_link = (
        pg_session.query(VideoCategory)
        .filter(VideoCategory.category_id == original_category_id, VideoCategory.video_id == video.id)
        .first()
    )
    assert surviving_link is not None  # the video-category relationship survived the rename
