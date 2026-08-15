from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.result import ResultDetailOut
from app.schemas.saved_result import SavedResultOut
from app.services import result_service, saved_result_service

router = APIRouter(prefix="/api/results", tags=["results"])


def _saved_to_out(saved) -> SavedResultOut:
    return SavedResultOut(
        saved_result_id=saved.id,
        result_id=saved.search_result_id,
        saved_at=saved.created_at,
        is_saved=True,
    )


# Same 404 whether the result is missing or not accessible to this user.
@router.get("/{result_id}", response_model=ResultDetailOut)
def read_result(
    result_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResultDetailOut:
    try:
        return result_service.get_result_detail(db, current_user, result_id)
    except result_service.ResultNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")


@router.post("/{result_id}/save", response_model=SavedResultOut)
def save_result(
    result_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedResultOut:
    try:
        saved = saved_result_service.save_result(db, current_user, result_id)
    except saved_result_service.ResultNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")
    except saved_result_service.ClipNotGeneratedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This scene needs to be generated before it can be saved.",
        )
    return _saved_to_out(saved)


# Idempotent: removing an already-absent saved row is not an error.
@router.delete("/{result_id}/save", status_code=status.HTTP_200_OK)
def unsave_result(
    result_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        saved_result_service.unsave_result(db, current_user, result_id)
    except saved_result_service.ResultNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")
    return {"message": "Removed from saved scenes."}


@router.get("/{result_id}/save-status")
def read_save_status(
    result_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    try:
        saved_result_service.get_accessible_result(db, current_user, result_id)
    except saved_result_service.ResultNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")
    return {"is_saved": saved_result_service.is_saved(db, current_user.id, result_id)}
