from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MediaStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaSourceType(str, Enum):
    USER_UPLOAD = "user_upload"
    ADMIN_PRELOADED = "admin_preloaded"


class MediaVisibility(str, Enum):
    PRIVATE = "private"
    SHARED = "shared"


class SubtitleSource(str, Enum):
    UPLOADED = "uploaded"
    EMBEDDED = "embedded"
    WHISPER = "whisper"
    NONE = "none"


class SearchType(str, Enum):
    EXACT_TEXT = "exact_text"
    SEMANTIC = "semantic"
    SPEECH_TO_TEXT = "speech_to_text"


class SearchScope(str, Enum):
    MY_LIBRARY = "my_library"
    SHARED_LIBRARY = "shared_library"
    BOTH = "both"


class SearchBackend(str, Enum):
    POSTGRESQL = "postgresql"
    ELASTICSEARCH = "elasticsearch"


class ProcessingStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
