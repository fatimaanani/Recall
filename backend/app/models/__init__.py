# Model registry, required for Alembic autogenerate

from app.models.user import User
from app.models.password_reset_token import PasswordResetToken
from app.models.video import Video
from app.models.category import Category
from app.models.video_category import VideoCategory
from app.models.transcript_segment import TranscriptSegment
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.generated_clip import GeneratedClip
from app.models.saved_result import SavedResult
from app.models.processing_log import ProcessingLog
from app.models.error_log import ErrorLog
from app.models.evaluation_test_case import EvaluationTestCase
from app.models.evaluation_result import EvaluationResult
from app.models.admin_message import AdminMessage
from app.models.admin_audit_log import AdminAuditLog

__all__ = [
    "User",
    "PasswordResetToken",
    "Video",
    "Category",
    "VideoCategory",
    "TranscriptSegment",
    "SearchQuery",
    "SearchResult",
    "GeneratedClip",
    "SavedResult",
    "ProcessingLog",
    "ErrorLog",
    "EvaluationTestCase",
    "EvaluationResult",
    "AdminMessage",
    "AdminAuditLog",
]
