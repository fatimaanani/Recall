from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    environment: str = "dev"
    cors_allowed_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    storage_root: str = "storage"
    max_upload_size_bytes: int = 5 * 1024 * 1024 * 1024
    # 2 MiB is generous for any real SRT/VTT file; rejects clearly wrong
    # uploads before parsing.
    max_subtitle_upload_size_bytes: int = 2 * 1024 * 1024

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    ffmpeg_timeout_seconds: int = 120

    whisper_model_size: str = "tiny"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    processing_temp_dir: str = "storage/tmp"
    # Stuck-processing safety net
    whisper_transcription_timeout_seconds: int = 7200

    whisper_max_no_speech_prob: float = 0.6
    whisper_hard_max_no_speech_prob: float = 0.9
    whisper_min_avg_logprob: float = -1.0
    whisper_max_compression_ratio: float = 2.4
    whisper_max_words_per_second: float = 4.0
    whisper_repetition_similarity: float = 0.85
    whisper_max_repetition_ratio: float = 0.60

    # embedding_model_name must keep producing 384-dim vectors to match
    # transcript_segments.embedding; a different-dimension model needs its
    # own migration.
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    # Caps how many segment texts go into one batched model.encode() call per video.
    embedding_batch_size: int = 32

    # Weights are validated (not silently normalized) so a bad .env value
    # fails loudly at startup.
    search_top_k_default: int = 20
    hybrid_keyword_weight: float = 0.5
    hybrid_semantic_weight: float = 0.5

    @model_validator(mode="after")
    def _validate_hybrid_weights(self) -> "Settings":
        if self.hybrid_keyword_weight < 0 or self.hybrid_semantic_weight < 0:
            raise ValueError("hybrid_keyword_weight and hybrid_semantic_weight must both be >= 0.")
        if (self.hybrid_keyword_weight + self.hybrid_semantic_weight) <= 0:
            raise ValueError("hybrid_keyword_weight + hybrid_semantic_weight must be > 0.")
        return self

    # merge_gap: segments this close together (seconds) get merged.
    # max_merged_duration: cap so merging never produces one unwieldy segment.
    # max_duration: safety split for a single already-long input cue.
    transcript_segment_merge_gap_seconds: float = 0.5
    transcript_segment_max_merged_duration_seconds: float = 15.0
    transcript_segment_max_duration_seconds: float = 30.0

    @model_validator(mode="after")
    def _validate_transcript_segment_settings(self) -> "Settings":
        for name in (
            "transcript_segment_merge_gap_seconds",
            "transcript_segment_max_merged_duration_seconds",
            "transcript_segment_max_duration_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0.")
        if self.transcript_segment_max_merged_duration_seconds > self.transcript_segment_max_duration_seconds:
            raise ValueError(
                "transcript_segment_max_merged_duration_seconds must not exceed "
                "transcript_segment_max_duration_seconds."
            )
        return self

    # Separate from the video upload/transcription limits above -- a search
    # query is a short spoken phrase, not a media upload.
    query_audio_max_size_bytes: int = 10 * 1024 * 1024
    query_transcription_timeout_seconds: int = 60

    clip_pre_buffer_seconds: float = 3.0
    clip_post_buffer_seconds: float = 3.0
    clip_min_duration_seconds: float = 5.0
    clip_max_duration_seconds: float = 120.0
    clip_generation_timeout_seconds: int = 60
    clip_max_merge_gap_seconds: float = 1.0

    @model_validator(mode="after")
    def _validate_clip_settings(self) -> "Settings":
        for name in (
            "clip_pre_buffer_seconds",
            "clip_post_buffer_seconds",
            "clip_min_duration_seconds",
            "clip_max_duration_seconds",
            "clip_max_merge_gap_seconds",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0.")
        if self.clip_min_duration_seconds > self.clip_max_duration_seconds:
            raise ValueError("clip_min_duration_seconds must not exceed clip_max_duration_seconds.")
        if self.clip_generation_timeout_seconds <= 0:
            raise ValueError("clip_generation_timeout_seconds must be > 0.")
        return self

    # Evaluation only, never used by real user search. Disabled by default;
    # no connection is attempted while this is False.
    elasticsearch_enabled: bool = False
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_index_name: str = "recall_evaluation_segments"
    elasticsearch_timeout_seconds: int = 10

    # In-memory, per-process sliding window -- see rate_limit.py for the
    # multi-worker caveat.
    rate_limit_login_max: int = 10
    rate_limit_login_window_seconds: float = 300.0
    rate_limit_register_max: int = 5
    rate_limit_register_window_seconds: float = 3600.0
    rate_limit_search_max: int = 60
    rate_limit_search_window_seconds: float = 60.0
    rate_limit_speech_search_max: int = 20
    rate_limit_speech_search_window_seconds: float = 60.0
    rate_limit_upload_max: int = 10
    rate_limit_upload_window_seconds: float = 3600.0
    rate_limit_password_reset_max: int = 5
    rate_limit_password_reset_window_seconds: float = 3600.0

    # frontend_base_url builds the reset link; email delivery is
    # development-only (logged to console), see password_reset_service.py.
    frontend_base_url: str = "http://localhost:5173"
    password_reset_token_expire_minutes: int = 30

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
