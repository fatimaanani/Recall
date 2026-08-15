"""A Saved Scene is a real SearchResult, whose GeneratedClip already exists, that the user deliberately bookmarked from Scene Viewer -- distinct from SearchResult.selected_at, which this module never touches. saved_results has no video_id/generated_clip_id column, so queries reach them through the search_result relationships."""

from __future__ import annotations

import dataclasses

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, contains_eager, joinedload

from app.enums import MediaVisibility
from app.models.generated_clip import GeneratedClip
from app.models.saved_result import SavedResult
from app.models.search_result import SearchResult
from app.models.user import User
from app.models.video import Video
from app.services import video_service


class ResultNotFoundError(Exception):
    """No such SearchResult, or its video isn't accessible -- same error either way, matching clip_service."""


class ClipNotGeneratedError(Exception):
    """The result has no GeneratedClip yet; saving is only allowed once one exists."""


def _can_access_video(user: User, video: Video) -> bool:
    return video.owner_id == user.id or video.visibility == MediaVisibility.SHARED


def _load_result(db: Session, result_id: int) -> SearchResult | None:
    return (
        db.query(SearchResult)
        .options(joinedload(SearchResult.video), joinedload(SearchResult.clip))
        .filter(SearchResult.id == result_id)
        .first()
    )


def get_accessible_result(db: Session, user: User, result_id: int) -> SearchResult:
    result = _load_result(db, result_id)
    if result is None or not _can_access_video(user, result.video):
        raise ResultNotFoundError()
    return result


def is_saved(db: Session, user_id: int, result_id: int) -> bool:
    return (
        db.query(SavedResult)
        .filter(SavedResult.user_id == user_id, SavedResult.search_result_id == result_id)
        .first()
        is not None
    )


# Idempotent: if already saved, returns the existing row instead of erroring.
def save_result(db: Session, user: User, result_id: int) -> SavedResult:
    result = get_accessible_result(db, user, result_id)
    if result.clip is None:
        raise ClipNotGeneratedError()

    existing = (
        db.query(SavedResult)
        .filter(SavedResult.user_id == user.id, SavedResult.search_result_id == result_id)
        .first()
    )
    if existing is not None:
        return existing

    saved = SavedResult(user_id=user.id, search_result_id=result_id)
    db.add(saved)
    try:
        db.commit()
    except IntegrityError:
        # Race: a concurrent request saved it first; return the row that now exists.
        db.rollback()
        existing = (
            db.query(SavedResult)
            .filter(SavedResult.user_id == user.id, SavedResult.search_result_id == result_id)
            .first()
        )
        if existing is not None:
            return existing
        raise
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(saved)
    return saved


# Idempotent: removing a saved row that doesn't exist is a no-op, not an error.
def unsave_result(db: Session, user: User, result_id: int) -> None:
    # Authorization still applies as defense in depth, even though a saved row couldn't exist without prior access.
    get_accessible_result(db, user, result_id)

    existing = (
        db.query(SavedResult)
        .filter(SavedResult.user_id == user.id, SavedResult.search_result_id == result_id)
        .first()
    )
    if existing is None:
        return
    db.delete(existing)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


@dataclasses.dataclass
class SavedScene:
    saved_result: SavedResult
    result: SearchResult
    clip: GeneratedClip
    video: Video


# Inner-joins through clip and query since a saved row always has both; contains_eager reuses
# those joined rows instead of issuing extra queries per row.
def list_saved_for_video(db: Session, user: User, video_id: int) -> list[SavedScene]:
    # Reuses the same owner-or-shared authorization as other video-scoped endpoints.
    video = video_service.get_video(db, user, video_id)

    rows = (
        db.query(SavedResult)
        .join(SavedResult.result)
        .join(SearchResult.clip)
        .join(SearchResult.query)
        .options(
            contains_eager(SavedResult.result).contains_eager(SearchResult.clip),
            contains_eager(SavedResult.result).contains_eager(SearchResult.query),
        )
        .filter(SavedResult.user_id == user.id, SearchResult.video_id == video_id)
        .order_by(SavedResult.created_at.desc())
        .all()
    )
    return [
        SavedScene(saved_result=row, result=row.result, clip=row.result.clip, video=video)
        for row in rows
    ]
