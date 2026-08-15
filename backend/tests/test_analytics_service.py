"""
test_analytics_service.py

Same real-PostgreSQL integration style as test_search_service.py's
pg_session tests (see conftest.py) -- analytics_service does real SQL
aggregation (func.avg/func.count/group by), which a MagicMock db cannot
meaningfully exercise, so these tests run against a real schema and are
skipped (not failed) when TEST_DATABASE_URL is unset.

1. Shared pg_* helpers
2. Date range resolution + previous-period calculation
3. Totals, grouping, and per-metric aggregates
4. Time-series ordering
5. Date filtering (rows outside the window are excluded)
6. Previous-period comparison (delta_percent)
7. Empty-dataset honesty (no fabricated numbers)
8. Pipeline health counts
9. No private data leakage (aggregate-only response shape)
"""

from __future__ import annotations

import datetime

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SearchScope, SearchType
from app.models.generated_clip import GeneratedClip
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.services import analytics_service

# ===========================================================================
# 1. Shared pg_* helpers
# ===========================================================================


def _pg_make_user(pg_session, **overrides) -> User:
    defaults = dict(
        full_name="Test User", username=f"analyticsuser{id(overrides)}",
        email=f"analytics{id(overrides)}@example.com", password_hash="x",
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


def _pg_make_query(pg_session, user_id, **overrides) -> SearchQuery:
    defaults = dict(
        user_id=user_id, query_text="test query", query_type=SearchType.EXACT_TEXT,
        search_scope=SearchScope.BOTH, results_found=1, response_time_ms=100.0,
        created_at=datetime.datetime.utcnow(),
    )
    defaults.update(overrides)
    query = SearchQuery(**defaults)
    pg_session.add(query)
    pg_session.flush()
    return query


def _pg_make_segment(pg_session, video_id, **overrides) -> TranscriptSegment:
    from app.enums import SubtitleSource

    defaults = dict(video_id=video_id, start_time=0.0, end_time=2.0, text="segment text", source=SubtitleSource.WHISPER)
    defaults.update(overrides)
    segment = TranscriptSegment(**defaults)
    pg_session.add(segment)
    pg_session.flush()
    return segment


def _pg_make_result(pg_session, query_id, video_id, **overrides) -> SearchResult:
    defaults = dict(
        query_id=query_id, video_id=video_id, rank_position=1, confidence_score=0.9,
        matched_text="matched text",
    )
    defaults.update(overrides)
    result = SearchResult(**defaults)
    pg_session.add(result)
    pg_session.flush()
    return result


def _pg_make_clip(pg_session, result_id, video_id, **overrides) -> GeneratedClip:
    defaults = dict(
        result_id=result_id, video_id=video_id, start_time=0.0, end_time=5.0,
        clip_path=f"clips/{video_id}/{result_id}.mp4", clip_url=f"/api/clips/{result_id}",
        created_at=datetime.datetime.utcnow(),
    )
    defaults.update(overrides)
    clip = GeneratedClip(**defaults)
    pg_session.add(clip)
    pg_session.flush()
    return clip


def _day(offset: int) -> datetime.datetime:
    """A fixed anchor date, offset in days, so tests aren't flaky around midnight."""
    anchor = datetime.datetime(2026, 6, 15, 12, 0, 0)
    return anchor + datetime.timedelta(days=offset)


# ===========================================================================
# 2. Date range resolution + previous-period calculation
# ===========================================================================


def test_resolve_date_range_defaults_to_trailing_30_days_when_both_bounds_missing():
    date_from, date_to = analytics_service.resolve_date_range(None, None)
    assert date_to == datetime.date.today()
    assert (date_to - date_from).days == analytics_service.DEFAULT_WINDOW_DAYS - 1


def test_resolve_date_range_rejects_from_after_to():
    with pytest.raises(ValueError):
        analytics_service.resolve_date_range(datetime.date(2026, 6, 10), datetime.date(2026, 6, 1))


def test_previous_period_is_immediately_preceding_equal_duration_window():
    date_from = datetime.date(2026, 6, 10)
    date_to = datetime.date(2026, 6, 19)  # 10-day window
    prev_from, prev_to = analytics_service._previous_period(date_from, date_to)
    assert prev_to == datetime.date(2026, 6, 9)
    assert (prev_to - prev_from).days == 9  # same 10-day duration


# ===========================================================================
# 3. Totals, grouping, and per-metric aggregates
# ===========================================================================


def test_queries_processed_and_average_response_time_reflect_real_rows(pg_session):
    user = _pg_make_user(pg_session, username="metricsuser1", email="metrics1@example.com")
    _pg_make_query(pg_session, user.id, response_time_ms=100.0, created_at=_day(0))
    _pg_make_query(pg_session, user.id, response_time_ms=200.0, created_at=_day(0))
    pg_session.commit()

    result = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    assert result.queries_processed.value == 2
    assert result.average_response_time_ms.value == pytest.approx(150.0)


def test_query_distribution_groups_by_search_type_with_correct_percentages(pg_session):
    user = _pg_make_user(pg_session, username="distuser1", email="dist1@example.com")
    _pg_make_query(pg_session, user.id, query_type=SearchType.EXACT_TEXT, created_at=_day(0))
    _pg_make_query(pg_session, user.id, query_type=SearchType.EXACT_TEXT, created_at=_day(0))
    _pg_make_query(pg_session, user.id, query_type=SearchType.EXACT_TEXT, created_at=_day(0))
    _pg_make_query(pg_session, user.id, query_type=SearchType.SEMANTIC, created_at=_day(0))
    pg_session.commit()

    result = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    by_type = {entry.search_type: entry for entry in result.query_distribution}
    assert by_type[SearchType.EXACT_TEXT].count == 3
    assert by_type[SearchType.EXACT_TEXT].percent == 75.0
    assert by_type[SearchType.SEMANTIC].count == 1
    assert by_type[SearchType.SEMANTIC].percent == 25.0
    assert result.total_queries == 4


def test_ready_media_transcript_segment_and_clip_counts_are_real(pg_session):
    user = _pg_make_user(pg_session, username="pipeuser1", email="pipe1@example.com")
    video = _pg_make_video(pg_session, user.id, status=MediaStatus.READY, uploaded_at=_day(0))
    _pg_make_segment(pg_session, video.id, text="a")
    _pg_make_segment(pg_session, video.id, text="b")
    query = _pg_make_query(pg_session, user.id, created_at=_day(0))
    result = _pg_make_result(pg_session, query.id, video.id)
    _pg_make_clip(pg_session, result.id, video.id, created_at=_day(0))
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    assert out.pipeline_health.media_processed == 1
    assert out.pipeline_health.transcript_segments_generated == 2
    assert out.pipeline_health.clips_created == 1
    assert out.media_files_indexed.value == 1


def test_failed_uploads_counted_separately_from_ready_media(pg_session):
    user = _pg_make_user(pg_session, username="faileduser1", email="failed1@example.com")
    _pg_make_video(pg_session, user.id, status=MediaStatus.FAILED, uploaded_at=_day(0))
    _pg_make_video(pg_session, user.id, status=MediaStatus.READY, uploaded_at=_day(0))
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    assert out.pipeline_health.failed_uploads == 1
    assert out.pipeline_health.media_processed == 1  # only the READY one


# ===========================================================================
# 4. Time-series ordering
# ===========================================================================


def test_response_time_series_is_ordered_by_date_and_split_by_query_type(pg_session):
    user = _pg_make_user(pg_session, username="seriesuser1", email="series1@example.com")
    _pg_make_query(pg_session, user.id, query_type=SearchType.EXACT_TEXT, response_time_ms=100.0, created_at=_day(1))
    _pg_make_query(pg_session, user.id, query_type=SearchType.SEMANTIC, response_time_ms=300.0, created_at=_day(1))
    _pg_make_query(pg_session, user.id, query_type=SearchType.EXACT_TEXT, response_time_ms=200.0, created_at=_day(0))
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(1).date()
    )
    series = out.response_time_series
    assert [point.date for point in series] == sorted(point.date for point in series)
    day1_point = next(p for p in series if p.date == _day(1).date())
    assert day1_point.exact_text_ms == 100.0
    assert day1_point.semantic_ms == 300.0
    assert day1_point.speech_to_text_ms is None


# ===========================================================================
# 5. Date filtering
# ===========================================================================


def test_rows_outside_the_date_window_are_excluded(pg_session):
    user = _pg_make_user(pg_session, username="filteruser1", email="filter1@example.com")
    _pg_make_query(pg_session, user.id, created_at=_day(0))  # inside
    _pg_make_query(pg_session, user.id, created_at=_day(-5))  # before window
    _pg_make_query(pg_session, user.id, created_at=_day(5))  # after window
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    assert out.queries_processed.value == 1


# ===========================================================================
# 6. Previous-period comparison
# ===========================================================================


def test_delta_percent_compares_against_immediately_preceding_period(pg_session):
    user = _pg_make_user(pg_session, username="deltauser1", email="delta1@example.com")
    _pg_make_query(pg_session, user.id, created_at=_day(0))
    _pg_make_query(pg_session, user.id, created_at=_day(0))
    _pg_make_query(pg_session, user.id, created_at=_day(-1))  # previous period (1-day window)
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    assert out.queries_processed.value == 2
    assert out.queries_processed.previous_value == 1
    assert out.queries_processed.delta_percent == 100.0


def test_delta_percent_is_none_when_no_previous_period_data_exists(pg_session):
    user = _pg_make_user(pg_session, username="nodeltauser1", email="nodelta1@example.com")
    _pg_make_query(pg_session, user.id, created_at=_day(0))
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    assert out.queries_processed.previous_value in (0, None)
    assert out.queries_processed.delta_percent is None  # never a fabricated 0% or infinite jump


# ===========================================================================
# 7. Empty-dataset honesty
# ===========================================================================


def test_empty_window_returns_zero_counts_and_empty_lists_not_fabricated_data(pg_session):
    far_future = datetime.date(2099, 1, 1)
    out = analytics_service.get_operational_analytics(pg_session, date_from=far_future, date_to=far_future)
    assert out.queries_processed.value == 0
    assert out.query_distribution == []
    assert out.response_time_series == []
    assert out.usage_insight is None  # build_usage_insight must not invent a sentence with no data
    assert out.average_response_time_ms.value == 0.0
    assert out.average_response_time_ms.previous_value is None


def test_usage_insight_mentions_only_real_usage_when_no_evaluation_data_given(pg_session):
    user = _pg_make_user(pg_session, username="insightuser1", email="insight1@example.com")
    _pg_make_query(pg_session, user.id, query_type=SearchType.SEMANTIC, created_at=_day(0))
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date(), best_accuracy_method=None
    )
    assert out.usage_insight == "Semantic Search is currently the most-used search method."


# ===========================================================================
# 9. No private data leakage
# ===========================================================================


def test_operational_analytics_response_never_carries_raw_query_text_or_user_identity(pg_session):
    user = _pg_make_user(pg_session, username="privacyuser1", email="privacy1@example.com")
    _pg_make_query(pg_session, user.id, query_text="a very private search phrase", created_at=_day(0))
    pg_session.commit()

    out = analytics_service.get_operational_analytics(
        pg_session, date_from=_day(0).date(), date_to=_day(0).date()
    )
    dumped = out.model_dump()
    serialized = str(dumped)
    assert "a very private search phrase" not in serialized
    assert "user_id" not in dumped
    assert "query_text" not in dumped
