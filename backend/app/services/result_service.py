"""Thin, read-only counterpart to clip_service.get_or_create_clip: loads a result's full "why this matched" context from resultId alone, since React Router's location.state is lost on refresh or direct navigation. Also computes Summary/Key Points for the clip's window via transcript_summary_service.py."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.enums import MediaVisibility
from app.models.search_result import SearchResult
from app.models.user import User
from app.models.video import Video
from app.models.video_category import VideoCategory
from app.schemas.result import ResultClipSummary, ResultDetailCategoryBrief, ResultDetailOut
from app.services import saved_result_service, transcript_summary_service


class ResultNotFoundError(Exception):
    """No such SearchResult, or its video isn't accessible -- same error either way, see saved_result_service."""


def _can_access_video(user: User, video: Video) -> bool:
    return video.owner_id == user.id or video.visibility == MediaVisibility.SHARED


def get_result_detail(db: Session, user: User, result_id: int) -> ResultDetailOut:
    result = (
        db.query(SearchResult)
        .options(
            joinedload(SearchResult.video)
            .joinedload(Video.category_links)
            .joinedload(VideoCategory.category),
            joinedload(SearchResult.query),
            joinedload(SearchResult.clip),
        )
        .filter(SearchResult.id == result_id)
        .first()
    )
    if result is None or not _can_access_video(user, result.video):
        raise ResultNotFoundError()

    video = result.video
    query = result.query
    clip = result.clip

    # Speech-to-Text queries have no query_text of their own; the Whisper transcription of the
    # submitted audio is the displayed "query", same fallback Results.jsx applies on the frontend.
    query_text = (
        query.transcribed_text if query.query_type.value == "speech_to_text" else query.query_text
    )

    clip_summary = None
    transcript_span_text = None
    summary = None
    key_points: list[str] = []
    if clip is not None:
        clip_summary = ResultClipSummary(
            generated_clip_id=clip.id,
            start_time=clip.start_time,
            end_time=clip.end_time,
            duration=clip.end_time - clip.start_time,
            clip_stream_url=clip.clip_url,
            is_audio_only=not video.mime_type.startswith("video/"),
        )
        # Summary/Key Points are derived from TranscriptSegment rows overlapping the generated
        # clip's window, not just the matched line.
        overlapping_segments = transcript_summary_service.select_overlapping_segments(
            db, video.id, clip.start_time, clip.end_time
        )
        transcript_span_text, summary, key_points = transcript_summary_service.build_scene_summary(
            overlapping_segments
        )

    return ResultDetailOut(
        result_id=result.id,
        video_id=video.id,
        video_title=video.title,
        media_type="video" if video.mime_type.startswith("video/") else "audio",
        transcript_segment_id=result.transcript_segment_id,
        matched_start_time=result.matched_start_time,
        matched_end_time=result.matched_end_time,
        matched_text=result.matched_text,
        confidence_score=result.confidence_score,
        keyword_score=result.keyword_score,
        semantic_score=result.semantic_score,
        rank_position=result.rank_position,
        query_text=query_text,
        query_type=query.query_type,
        search_scope=query.search_scope,
        categories=[
            ResultDetailCategoryBrief(id=link.category.id, name=link.category.name)
            for link in video.category_links
        ],
        clip=clip_summary,
        is_saved=saved_result_service.is_saved(db, user.id, result.id),
        transcript_span_text=transcript_span_text,
        summary=summary,
        key_points=key_points,
    )
