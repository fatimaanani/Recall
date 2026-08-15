from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.user import User
from app.models.video import Video
from app.models.video_category import VideoCategory


class CategoryNameAlreadyExistsError(Exception):
    pass


class CategoryNotFoundError(Exception):
    pass


class VideoNotFoundError(Exception):
    pass


class AlreadyAssignedError(Exception):
    pass


class NotAssignedError(Exception):
    pass


# Only rename rejects a whitespace-only name; create_category does not guard against it.
class EmptyCategoryNameError(Exception):
    pass


def create_category(db: Session, user: User, name: str) -> Category:
    name = name.strip()
    category = Category(user_id=user.id, name=name)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CategoryNameAlreadyExistsError()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(category)
    return category


def list_categories(db: Session, user: User) -> list[tuple[Category, int]]:
    return (
        db.query(Category, func.count(VideoCategory.video_id))
        .outerjoin(VideoCategory, VideoCategory.category_id == Category.id)
        .filter(Category.user_id == user.id)
        .group_by(Category.id)
        .order_by(Category.name)
        .all()
    )


def delete_category(db: Session, user: User, category_id: int) -> None:
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )
    if category is None:
        raise CategoryNotFoundError()

    db.delete(category)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _get_owned_category_or_none(db: Session, user: User, category_id: int) -> Category | None:
    return (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )


def get_category_with_videos(db: Session, user: User, category_id: int) -> tuple[Category, list[Video]]:
    category = _get_owned_category_or_none(db, user, category_id)
    if category is None:
        raise CategoryNotFoundError()

    videos = (
        db.query(Video)
        .join(VideoCategory, VideoCategory.video_id == Video.id)
        .options(selectinload(Video.category_links).selectinload(VideoCategory.category))
        .filter(VideoCategory.category_id == category_id)
        .order_by(Video.uploaded_at.desc())
        .all()
    )
    return category, videos


def rename_category(db: Session, user: User, category_id: int, new_name: str) -> tuple[Category, int]:
    category = _get_owned_category_or_none(db, user, category_id)
    if category is None:
        raise CategoryNotFoundError()

    trimmed_name = new_name.strip()
    if not trimmed_name:
        raise EmptyCategoryNameError()

    category.name = trimmed_name
    try:
        db.commit()
    except IntegrityError:
        # uq_categories_user_id_name constraint violation.
        db.rollback()
        raise CategoryNameAlreadyExistsError()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(category)

    video_count = (
        db.query(func.count(VideoCategory.video_id))
        .filter(VideoCategory.category_id == category.id)
        .scalar()
    )
    return category, int(video_count or 0)


def assign_video(db: Session, user: User, video_id: int, category_id: int) -> None:
    if _get_owned_category_or_none(db, user, category_id) is None:
        raise CategoryNotFoundError()

    video = db.query(Video).filter(Video.id == video_id, Video.owner_id == user.id).first()
    if video is None:
        raise VideoNotFoundError()

    existing = (
        db.query(VideoCategory)
        .filter(VideoCategory.video_id == video_id, VideoCategory.category_id == category_id)
        .first()
    )
    if existing is not None:
        raise AlreadyAssignedError()

    db.add(VideoCategory(video_id=video_id, category_id=category_id))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def remove_video(db: Session, user: User, video_id: int, category_id: int) -> None:
    if _get_owned_category_or_none(db, user, category_id) is None:
        raise CategoryNotFoundError()

    link = (
        db.query(VideoCategory)
        .filter(VideoCategory.video_id == video_id, VideoCategory.category_id == category_id)
        .first()
    )
    if link is None:
        raise NotAssignedError()

    db.delete(link)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
