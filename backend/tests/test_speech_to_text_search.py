"""
test_speech_to_text_search.py

1. Shared helpers
2. Unit tests -- whisper_processor.evaluate_segment / is_hallucination_dominated
   (see whisper_processor.py's own docstring for why they live there
   rather than in media_processing_service.py)
3. Unit tests -- audio validation (extension, magic bytes, oversized)
4. Unit tests -- transcription failures (ffmpeg/whisper failure or timeout,
   empty/unusable transcription, hallucination-dominated transcription)
5. Unit tests -- execute_speech_to_text_search orchestration (mocked DB +
   mocked retrieval + mocked whisper_processor calls)
6. Unit tests -- temporary file cleanup (every path, success and failure)
7. Integration tests -- real PostgreSQL + pgvector (TEST_DATABASE_URL)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.enums import (
    MediaSourceType,
    MediaStatus,
    MediaVisibility,
    SearchScope,
    SearchType,
    SubtitleSource,
)
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.processing.ffmpeg_processor import ProcessingError
from app.processing.whisper_processor import WhisperSegment, evaluate_segment, is_hallucination_dominated
from app.services import search_service


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

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
        has_embeddings=False,
    )
    defaults.update(overrides)
    return Video(**defaults)


def _make_raw_match(**overrides) -> search_service._RawMatch:
    defaults = dict(
        transcript_segment_id=1,
        video=_make_video(),
        start_time=0.0,
        end_time=2.0,
        text="hello world",
    )
    defaults.update(overrides)
    return search_service._RawMatch(**defaults)


# Clean-by-default WhisperSegment -- well inside every hallucination-filter
# threshold's default value, so it passes evaluate_segment's "normal" path
# without depending on exact .env-tunable numbers.
def _make_whisper_segment(**overrides) -> WhisperSegment:
    defaults = dict(
        start=0.0,
        end=2.0,
        text="recursion is when a function calls itself",
        no_speech_prob=0.1,
        avg_logprob=-0.2,
        compression_ratio=1.2,
    )
    defaults.update(overrides)
    return WhisperSegment(**defaults)


# Same mock-DB convention as test_search_service.py -- simulates
# id-assignment on flush so post-flush SearchResultOut construction works.
def _make_mock_db():
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append

    def _flush():
        next_id = 1
        for obj in added:
            if getattr(obj, "id", None) is None:
                obj.id = next_id
            next_id = obj.id + 1

    mock_db.flush.side_effect = _flush
    mock_db.commit.side_effect = lambda: None
    mock_db.refresh.side_effect = lambda obj: None
    mock_db._added = added
    return mock_db


# Duck-typed settings, only the attributes execute_speech_to_text_search /
# _persist_and_build_response actually read. processing_temp_dir points at
# pytest's own tmp_path by default so tests never touch backend/storage/tmp.
def _make_settings(tmp_path, **overrides):
    from types import SimpleNamespace
    defaults = dict(
        query_audio_max_size_bytes=10 * 1024 * 1024,
        processing_temp_dir=str(tmp_path),
        query_transcription_timeout_seconds=60,
        hybrid_keyword_weight=0.5,
        hybrid_semantic_weight=0.5,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# Minimal valid signatures, matching file_validation._matches_known_signature
_VALID_WAV_HEAD = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 32
_VALID_MP4_HEAD = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32


# ===========================================================================
# 2. Unit tests -- whisper_processor.evaluate_segment / is_hallucination_dominated
#    (post-relocation behavior lock-in -- item 21 of the approved test plan)
# ===========================================================================

def test_evaluate_segment_accepts_clean_segment_as_normal():
    segment = _make_whisper_segment()
    accepted, path, reasons = evaluate_segment(segment)
    assert accepted is True
    assert path == "normal"
    assert reasons == []


def test_evaluate_segment_rejects_blank_text():
    segment = _make_whisper_segment(text="   ")
    accepted, path, reasons = evaluate_segment(segment)
    assert accepted is False
    assert path == "rejected"
    assert "blank text" in reasons


def test_evaluate_segment_rejects_low_avg_logprob():
    segment = _make_whisper_segment(avg_logprob=-5.0)
    accepted, path, reasons = evaluate_segment(segment)
    assert accepted is False
    assert path == "rejected"
    assert any("avg_logprob" in r for r in reasons)


def test_evaluate_segment_relief_path_for_high_no_speech_prob_with_clean_signals():
    # no_speech_prob above the soft ceiling (0.6 default) but below the hard
    # ceiling (0.9 default), every other signal clean -> "relief", accepted.
    segment = _make_whisper_segment(no_speech_prob=0.75)
    accepted, path, reasons = evaluate_segment(segment)
    assert accepted is True
    assert path == "relief"


def test_is_hallucination_dominated_false_for_distinct_segments():
    segments = [
        _make_whisper_segment(text="recursion is when a function calls itself"),
        _make_whisper_segment(text="iteration uses a loop instead"),
        _make_whisper_segment(text="both approaches can solve the same problem"),
    ]
    assert is_hallucination_dominated(segments) is False


def test_is_hallucination_dominated_true_for_repeated_identical_text():
    segments = [_make_whisper_segment(text="the the the") for _ in range(3)]
    assert is_hallucination_dominated(segments) is True


def test_is_hallucination_dominated_false_below_minimum_segment_count():
    # Fewer than _MIN_SEGMENTS_FOR_REPETITION_CHECK (3) -- never flagged,
    # regardless of repetition.
    segments = [_make_whisper_segment(text="same") for _ in range(2)]
    assert is_hallucination_dominated(segments) is False


# ===========================================================================
# 3. Unit tests -- audio validation
# ===========================================================================

def test_execute_speech_to_text_search_rejects_unsupported_extension(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))

    with pytest.raises(search_service.InvalidQueryAudioError):
        search_service.execute_speech_to_text_search(
            mock_db, user, b"irrelevant content", "query.txt", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()


def test_execute_speech_to_text_search_rejects_video_extension_even_with_valid_signature(mocker, tmp_path):
    # mp4 is a recognized extension+signature (Uploads module accepts it),
    # but this is a spoken search query, not a media upload -- only audio
    # extensions are accepted here.
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))

    with pytest.raises(search_service.InvalidQueryAudioError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_MP4_HEAD, "query.mp4", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()


def test_execute_speech_to_text_search_rejects_magic_byte_mismatch(mocker, tmp_path):
    # .wav extension, but the content doesn't start with RIFF/WAVE --
    # extension alone is never trusted.
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))

    with pytest.raises(search_service.InvalidQueryAudioError):
        search_service.execute_speech_to_text_search(
            mock_db, user, b"not actually a wav file at all", "query.wav", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()


def test_execute_speech_to_text_search_rejects_oversized_audio(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(
        search_service, "get_settings",
        return_value=_make_settings(tmp_path, query_audio_max_size_bytes=10),
    )

    with pytest.raises(search_service.QueryAudioTooLargeError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()


# ===========================================================================
# 4. Unit tests -- transcription failures
# ===========================================================================

def test_execute_speech_to_text_search_wraps_corrupt_audio_extraction_failure(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(
        search_service.whisper_processor, "extract_audio",
        side_effect=ProcessingError("ffmpeg could not extract an audio track from this file"),
    )

    with pytest.raises(search_service.QueryTranscriptionError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    # error_log_service.log_error (2026-08-08) stages exactly one row (the
    # ErrorLog itself) on this path -- see test_search_error_logging.py.
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1
    assert list(tmp_path.iterdir()) == []  # temp file cleaned up despite the failure


def test_execute_speech_to_text_search_wraps_whisper_timeout(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        side_effect=ProcessingError("Whisper transcription exceeded the configured timeout of 60 seconds"),
    )

    with pytest.raises(search_service.QueryTranscriptionError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    # error_log_service.log_error (2026-08-08) stages exactly one row (the
    # ErrorLog itself) on this path -- see test_search_error_logging.py.
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1
    assert list(tmp_path.iterdir()) == []


def test_execute_speech_to_text_search_wraps_whisper_failure(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        side_effect=ProcessingError("Whisper transcription failed: model error"),
    )

    with pytest.raises(search_service.QueryTranscriptionError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    # error_log_service.log_error (2026-08-08) stages exactly one row (the
    # ErrorLog itself) on this path -- see test_search_error_logging.py.
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1
    assert list(tmp_path.iterdir()) == []


def test_execute_speech_to_text_search_rejects_empty_transcription(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(search_service.whisper_processor, "transcribe_audio", return_value=[])

    with pytest.raises(search_service.EmptyTranscriptionError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_execute_speech_to_text_search_rejects_whitespace_only_segments(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="   ")],
    )

    with pytest.raises(search_service.EmptyTranscriptionError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()


def test_execute_speech_to_text_search_rejects_hallucination_dominated_transcription(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="the the the") for _ in range(3)],
    )

    with pytest.raises(search_service.EmptyTranscriptionError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    mock_db.add.assert_not_called()
    assert list(tmp_path.iterdir()) == []


# ===========================================================================
# 5. Unit tests -- execute_speech_to_text_search orchestration
# ===========================================================================

def test_execute_speech_to_text_search_valid_request_runs_both_branches_and_persists(mocker, tmp_path):
    user = _make_user()
    video = _make_video(id=3, owner_id=user.id, title="Data Structures Lecture")
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="a procedure that calls itself repeatedly")],
    )
    mock_exact = mocker.patch.object(
        search_service, "_run_exact_text_search",
        return_value=[search_service._RawMatch(
            transcript_segment_id=10, video=video, start_time=1.0, end_time=3.0,
            text="recursion example", raw_keyword_rank=0.8,
        )],
    )
    mock_semantic = mocker.patch.object(
        search_service, "_run_semantic_search",
        return_value=[search_service._RawMatch(
            transcript_segment_id=11, video=video, start_time=5.0, end_time=7.0,
            text="a function calling itself", raw_cosine_distance=0.1,
        )],
    )

    response = search_service.execute_speech_to_text_search(
        mock_db, user, _VALID_WAV_HEAD, "my query.wav", SearchScope.BOTH, 20
    )

    # Item 10: both branches actually called, with the transcribed text.
    mock_exact.assert_called_once()
    mock_semantic.assert_called_once()
    assert mock_exact.call_args.args[3] == "a procedure that calls itself repeatedly"
    assert mock_semantic.call_args.args[3] == "a procedure that calls itself repeatedly"

    assert response.query_type == SearchType.SPEECH_TO_TEXT
    assert response.transcribed_text == "a procedure that calls itself repeatedly"
    assert response.result_count == 2
    assert list(tmp_path.iterdir()) == []  # item 19: cleaned up after success


def test_execute_speech_to_text_search_merges_duplicate_segment_and_keeps_both_scores(mocker, tmp_path):
    user = _make_user()
    video = _make_video(id=3, owner_id=user.id)
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="recursion")],
    )
    mocker.patch.object(
        search_service, "_run_exact_text_search",
        return_value=[search_service._RawMatch(
            transcript_segment_id=42, video=video, start_time=0.0, end_time=2.0,
            text="recursion explained", raw_keyword_rank=1.0,
        )],
    )
    mocker.patch.object(
        search_service, "_run_semantic_search",
        return_value=[search_service._RawMatch(
            transcript_segment_id=42, video=video, start_time=0.0, end_time=2.0,
            text="recursion explained", raw_cosine_distance=0.0,
        )],
    )

    response = search_service.execute_speech_to_text_search(
        mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
    )

    assert response.result_count == 1  # merged into one row, not two
    result = response.results[0]
    assert result.keyword_score is not None
    assert result.semantic_score is not None
    assert result.confidence_score == pytest.approx(0.5 * result.keyword_score + 0.5 * result.semantic_score)


def test_execute_speech_to_text_search_persists_query_type_text_and_filename(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="what is a binary search tree")],
    )
    mocker.patch.object(search_service, "_run_exact_text_search", return_value=[])
    mocker.patch.object(search_service, "_run_semantic_search", return_value=[])

    response = search_service.execute_speech_to_text_search(
        mock_db, user, _VALID_WAV_HEAD, "recording_42.wav", SearchScope.BOTH, 20
    )

    persisted_queries = [obj for obj in mock_db._added if isinstance(obj, SearchQuery)]
    assert len(persisted_queries) == 1
    query = persisted_queries[0]
    # Item 13/14/15: query_type, query_text == transcribed_text, filename.
    assert query.query_type == SearchType.SPEECH_TO_TEXT
    assert query.query_text == "what is a binary search tree"
    assert query.transcribed_text == "what is a binary search tree"
    assert query.original_audio_filename == "recording_42.wav"
    assert response.transcribed_text == "what is a binary search tree"
    # No permanent local path is retained for query audio.
    assert query.audio_query_path is None


def test_execute_speech_to_text_search_zero_results_still_persists_query(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="nothing will match this")],
    )
    mocker.patch.object(search_service, "_run_exact_text_search", return_value=[])
    mocker.patch.object(search_service, "_run_semantic_search", return_value=[])

    response = search_service.execute_speech_to_text_search(
        mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
    )

    assert response.result_count == 0
    persisted_queries = [obj for obj in mock_db._added if isinstance(obj, SearchQuery)]
    assert len(persisted_queries) == 1
    assert persisted_queries[0].results_found == 0
    mock_db.commit.assert_called_once()


def test_execute_speech_to_text_search_scope_passed_through_unchanged(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="scope test query")],
    )
    mock_exact = mocker.patch.object(search_service, "_run_exact_text_search", return_value=[])
    mock_semantic = mocker.patch.object(search_service, "_run_semantic_search", return_value=[])

    search_service.execute_speech_to_text_search(
        mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.MY_LIBRARY, 20
    )

    assert mock_exact.call_args.args[2] == SearchScope.MY_LIBRARY
    assert mock_semantic.call_args.args[2] == SearchScope.MY_LIBRARY


def test_execute_speech_to_text_search_wraps_exact_text_sqlalchemy_error(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="query")],
    )
    mocker.patch.object(search_service, "_run_exact_text_search", side_effect=SQLAlchemyError("db exploded"))

    with pytest.raises(search_service.RetrievalError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1
    assert list(tmp_path.iterdir()) == []


def test_execute_speech_to_text_search_wraps_semantic_embedding_error(mocker, tmp_path):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="query")],
    )
    mocker.patch.object(search_service, "_run_exact_text_search", return_value=[])
    mocker.patch.object(
        search_service, "_run_semantic_search", side_effect=ProcessingError("model unavailable")
    )

    with pytest.raises(search_service.SemanticEmbeddingError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1
    assert list(tmp_path.iterdir()) == []


def test_execute_speech_to_text_search_rolls_back_on_flush_failure(mocker, tmp_path):
    user = _make_user()
    video = _make_video()
    mock_db = _make_mock_db()
    mock_db.flush.side_effect = SQLAlchemyError("constraint violation")
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="query")],
    )
    mocker.patch.object(
        search_service, "_run_exact_text_search",
        return_value=[search_service._RawMatch(
            transcript_segment_id=1, video=video, start_time=0.0, end_time=1.0,
            text="x", raw_keyword_rank=1.0,
        )],
    )
    mocker.patch.object(search_service, "_run_semantic_search", return_value=[])

    with pytest.raises(SQLAlchemyError):
        search_service.execute_speech_to_text_search(
            mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
        )
    # Item 18: rollback on persistence failure.
    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()
    # Item 20: temp files still cleaned up despite the persistence failure.
    assert list(tmp_path.iterdir()) == []


# ===========================================================================
# 6. Unit tests -- temporary file cleanup, explicit filesystem assertions
# ===========================================================================

def test_execute_speech_to_text_search_writes_and_removes_raw_audio_file(mocker, tmp_path):
    # Directly observes the raw upload actually being written to disk (not
    # just mocked away) and then removed -- stronger than only checking the
    # directory is empty at the end, confirms a real write+cleanup cycle.
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))

    seen_during_call = {}

    def _fake_extract_audio(source_path, dest_path):
        # The raw file must exist on disk at this point in the flow.
        seen_during_call["raw_exists"] = source_path.exists()
        seen_during_call["raw_path"] = source_path

    mocker.patch.object(search_service.whisper_processor, "extract_audio", side_effect=_fake_extract_audio)
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="query")],
    )
    mocker.patch.object(search_service, "_run_exact_text_search", return_value=[])
    mocker.patch.object(search_service, "_run_semantic_search", return_value=[])

    search_service.execute_speech_to_text_search(
        mock_db, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
    )

    assert seen_during_call["raw_exists"] is True
    assert not seen_during_call["raw_path"].exists()  # removed after the call
    assert list(tmp_path.iterdir()) == []


# ===========================================================================
# 7. Integration tests -- real PostgreSQL + pgvector (TEST_DATABASE_URL)
# ===========================================================================

def _pg_make_user(pg_session, **overrides) -> User:
    defaults = dict(
        full_name="Test User", username=f"speechuser{id(overrides)}",
        email=f"speech{id(overrides)}@example.com", password_hash="x",
    )
    defaults.update(overrides)
    user = User(**defaults)
    pg_session.add(user)
    pg_session.flush()
    return user


def _pg_make_video(pg_session, owner_id, **overrides) -> Video:
    defaults = dict(
        owner_id=owner_id, title="Video", original_filename="v.mp4",
        file_path=f"videos/{owner_id}/v.mp4", file_size_bytes=1024, mime_type="video/mp4",
        status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    video = Video(**defaults)
    pg_session.add(video)
    pg_session.flush()
    return video


def _pg_make_segment(pg_session, video_id, text, **overrides) -> TranscriptSegment:
    defaults = dict(video_id=video_id, start_time=0.0, end_time=2.0, text=text, source=SubtitleSource.WHISPER)
    defaults.update(overrides)
    segment = TranscriptSegment(**defaults)
    pg_session.add(segment)
    pg_session.flush()
    return segment


def test_execute_speech_to_text_search_end_to_end_hybrid_in_postgres(pg_session, mocker, tmp_path):
    user = _pg_make_user(pg_session, username="speechuser1", email="speech1@example.com")
    video = _pg_make_video(pg_session, user.id, has_embeddings=True)

    near_vector = [1.0] + [0.0] * 383
    # Same segment matches both branches: exact text ("recursion") and
    # semantic (embedding mocked to be identical to the query vector) --
    # the first genuinely real dual-branch merge in this project's test
    # suite, against a real database.
    segment = _pg_make_segment(pg_session, video.id, "recursion is a function calling itself", embedding=near_vector)
    pg_session.commit()

    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(
        tmp_path, hybrid_keyword_weight=0.5, hybrid_semantic_weight=0.5,
    ))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="recursion")],
    )
    mocker.patch.object(search_service.embedding_processor, "generate_embeddings", return_value=[near_vector])

    response = search_service.execute_speech_to_text_search(
        pg_session, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
    )

    assert response.result_count == 1
    result = response.results[0]
    assert result.keyword_score is not None
    assert result.semantic_score is not None

    persisted_query = pg_session.query(SearchQuery).filter(SearchQuery.id == response.search_query_id).one()
    assert persisted_query.query_type == SearchType.SPEECH_TO_TEXT
    assert persisted_query.query_text == "recursion"
    assert persisted_query.transcribed_text == "recursion"
    assert persisted_query.original_audio_filename == "query.wav"
    assert persisted_query.audio_query_path is None

    persisted_results = pg_session.query(SearchResult).filter(SearchResult.query_id == persisted_query.id).all()
    assert len(persisted_results) == 1
    assert persisted_results[0].transcript_segment_id == segment.id
    assert persisted_results[0].keyword_score is not None
    assert persisted_results[0].semantic_score is not None

    assert list(tmp_path.iterdir()) == []


def test_execute_speech_to_text_search_zero_result_persisted_in_postgres(pg_session, mocker, tmp_path):
    user = _pg_make_user(pg_session, username="speechuser2", email="speech2@example.com")

    mocker.patch.object(search_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(search_service.whisper_processor, "extract_audio")
    mocker.patch.object(
        search_service.whisper_processor, "transcribe_audio",
        return_value=[_make_whisper_segment(text="nothing matches this at all")],
    )

    response = search_service.execute_speech_to_text_search(
        pg_session, user, _VALID_WAV_HEAD, "query.wav", SearchScope.BOTH, 20
    )

    assert response.result_count == 0
    persisted_query = pg_session.query(SearchQuery).filter(SearchQuery.id == response.search_query_id).one()
    assert persisted_query.results_found == 0
    assert persisted_query.query_type == SearchType.SPEECH_TO_TEXT
