from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.search_query import SearchQuery
from app.models.user import User


class InvalidHistoryLimitError(Exception):
    """limit outside the allowed 1-100 range."""


# No role branch: search history is inherently personal, so "no admin bypass" is true by
# construction rather than a role check that could be forgotten.
def _owner_predicate(user: User):
    return SearchQuery.user_id == user.id


def list_search_history(db: Session, user: User, limit: int) -> list[SearchQuery]:
    if limit < 1 or limit > 100:
        raise InvalidHistoryLimitError("limit must be between 1 and 100.")

    return (
        db.query(SearchQuery)
        .filter(_owner_predicate(user))
        .order_by(SearchQuery.created_at.desc())
        .limit(limit)
        .all()
    )
