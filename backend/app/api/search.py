from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.enums import SearchScope
from app.models.user import User
from app.schemas.search import SearchHistoryEntryOut, SearchRequest, SearchResponse
from app.services import search_history_service, search_service
from app.utils.rate_limit import rate_limit_by_user

router = APIRouter(prefix="/api/search", tags=["search"])
_settings = get_settings()

# User-keyed since both routes require auth; speech search has its own
# lower limit since it runs a full transcription per request.
_search_rate_limit = rate_limit_by_user(
    "search_text", _settings.rate_limit_search_max, _settings.rate_limit_search_window_seconds
)
_speech_search_rate_limit = rate_limit_by_user(
    "search_speech", _settings.rate_limit_speech_search_max, _settings.rate_limit_speech_search_window_seconds
)


# speech_to_text is a valid SearchType elsewhere but is rejected here; spoken
# queries go through /speech below.
@router.post("", response_model=SearchResponse, status_code=status.HTTP_200_OK)
def search(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_search_rate_limit),
) -> SearchResponse:
    try:
        return search_service.execute_search(db, current_user, payload)
    except search_service.EmptyQueryTextError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Search query can't be empty.",
        )
    except search_service.UnsupportedSearchMethodError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Speech-to-Text search is not available yet.",
        )
    except search_service.SemanticEmbeddingError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Semantic search is temporarily unavailable. Please try again.",
        )
    except search_service.RetrievalError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again.",
        )


# Always returns only the caller's own history, regardless of role.
@router.get("/history", response_model=list[SearchHistoryEntryOut], status_code=status.HTTP_200_OK)
def get_search_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SearchHistoryEntryOut]:
    try:
        entries = search_history_service.list_search_history(db, current_user, limit)
    except search_history_service.InvalidHistoryLimitError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return [SearchHistoryEntryOut.model_validate(entry) for entry in entries]


@router.post("/speech", response_model=SearchResponse, status_code=status.HTTP_200_OK)
async def search_by_speech(
    audio: UploadFile = File(...),
    search_scope: SearchScope = Form(default=SearchScope.BOTH),
    limit: int | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_speech_search_rate_limit),
) -> SearchResponse:
    settings = get_settings()
    effective_limit = limit if limit is not None else settings.search_top_k_default
    if effective_limit < 1 or effective_limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100.",
        )

    audio_bytes = await audio.read()

    try:
        return search_service.execute_speech_to_text_search(
            db, current_user, audio_bytes, audio.filename or "audio",
            search_scope, effective_limit,
        )
    except search_service.QueryAudioTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Query audio exceeds the "
                f"{settings.query_audio_max_size_bytes // (1024 * 1024)} MiB limit."
            ),
        )
    except search_service.InvalidQueryAudioError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except search_service.EmptyTranscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except search_service.QueryTranscriptionError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Speech-to-Text transcription failed. Please try again.",
        )
    except search_service.SemanticEmbeddingError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Semantic search is temporarily unavailable. Please try again.",
        )
    except search_service.RetrievalError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again.",
        )
