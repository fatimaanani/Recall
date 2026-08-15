from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryDetailOut,
    CategoryOut,
    CategoryRenameRequest,
)
from app.schemas.video import video_to_out
from app.services import category_service

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    try:
        category = category_service.create_category(db, current_user, payload.name)
    except category_service.CategoryNameAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a collection with this name.",
        )
    return CategoryOut(
        id=category.id, name=category.name, video_count=0, created_at=category.created_at
    )


@router.get("", response_model=list[CategoryOut])
def list_categories(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CategoryOut]:
    rows = category_service.list_categories(db, current_user)
    return [
        CategoryOut(id=c.id, name=c.name, video_count=count, created_at=c.created_at)
        for c, count in rows
    ]


@router.get("/{category_id}", response_model=CategoryDetailOut)
def read_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryDetailOut:
    try:
        category, videos = category_service.get_category_with_videos(db, current_user, category_id)
    except category_service.CategoryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return CategoryDetailOut(
        id=category.id,
        name=category.name,
        video_count=len(videos),
        created_at=category.created_at,
        videos=[video_to_out(v) for v in videos],
    )


@router.patch("/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: int,
    payload: CategoryRenameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    try:
        category, video_count = category_service.rename_category(
            db, current_user, category_id, payload.name
        )
    except category_service.CategoryNotFoundError:
        # Same 404 whether the category doesn't exist or belongs to someone else,
        # so ownership isn't leaked.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    except category_service.EmptyCategoryNameError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Collection name can't be empty.",
        )
    except category_service.CategoryNameAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a collection with this name.",
        )
    return CategoryOut(
        id=category.id, name=category.name, video_count=video_count, created_at=category.created_at
    )


@router.delete("/{category_id}", status_code=status.HTTP_200_OK)
def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        category_service.delete_category(db, current_user, category_id)
    except category_service.CategoryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return {"message": "Collection deleted successfully."}


@router.post("/{category_id}/videos/{video_id}", status_code=status.HTTP_201_CREATED)
def assign_video_to_category(
    category_id: int,
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        category_service.assign_video(db, current_user, video_id, category_id)
    except category_service.CategoryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    except category_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    except category_service.AlreadyAssignedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This video is already in this collection.",
        )
    return {"message": "Video added to collection."}


@router.delete("/{category_id}/videos/{video_id}", status_code=status.HTTP_200_OK)
def remove_video_from_category(
    category_id: int,
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        category_service.remove_video(db, current_user, video_id, category_id)
    except category_service.CategoryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    except category_service.NotAssignedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This video is not in this collection.",
        )
    return {"message": "Video removed from collection."}
