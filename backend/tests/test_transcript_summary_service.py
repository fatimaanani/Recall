"""
test_transcript_summary_service.py

1. Text-processing unit tests (no database) -- combine/dedup, span-level
   behavior, and the build_scene_summary entry point
1b. Quality-cleanup pipeline (2026-08-06) -- discourse-prefix stripping,
   dangling-connector/meta-reference/low-content rejection, the
   lowercase-first-sentence-orphan rule, and the exact previously-reported
   low-quality output as a named regression test
2. Database integration (pg_session) -- select_overlapping_segments' real
   overlap query: chronological order, boundary conditions, only the
   requested video
"""

from __future__ import annotations

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource, UserRole
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.services import transcript_summary_service as svc

# ===========================================================================
# 1. Text-processing unit tests
# ===========================================================================


def _seg(text, start=0.0, end=1.0, id_=1):
    return TranscriptSegment(id=id_, video_id=1, start_time=start, end_time=end, text=text, source=SubtitleSource.WHISPER)


def test_combine_segment_texts_joins_in_order():
    segments = [_seg("Recursion is a function calling itself.", id_=1), _seg("It needs a base case.", id_=2)]
    span, summary, points = svc.build_scene_summary(segments)
    assert span == "Recursion is a function calling itself. It needs a base case."
    assert summary == span


def test_empty_segment_list_returns_all_none():
    span, summary, points = svc.build_scene_summary([])
    assert span is None
    assert summary is None
    assert points == []


def test_immediate_duplicate_whisper_text_is_collapsed():
    # Same phrase transcribed twice in a row -- a known Whisper artifact --
    # is collapsed to one occurrence. A repeat with real content between is
    # left alone (tested separately below).
    segments = [
        _seg("Binary search trees are ordered.", id_=1),
        _seg("Binary search trees are ordered.", id_=2),
        _seg("Each node has at most two children.", id_=3),
    ]
    span, _summary, _points = svc.build_scene_summary(segments)
    assert span == "Binary search trees are ordered. Each node has at most two children."


def test_non_adjacent_repeat_is_preserved():
    segments = [
        _seg("Let's begin.", id_=1),
        _seg("Recursion needs a base case.", id_=2),
        _seg("Let's begin.", id_=3),
    ]
    span, _summary, _points = svc.build_scene_summary(segments)
    assert span == "Let's begin. Recursion needs a base case. Let's begin."


def test_null_and_empty_text_segments_are_skipped():
    segments = [_seg("", id_=1), _seg(None, id_=2), _seg("Real content here.", id_=3)]
    span, _summary, _points = svc.build_scene_summary(segments)
    assert span == "Real content here."


def test_all_empty_text_segments_returns_none():
    segments = [_seg("", id_=1), _seg(None, id_=2)]
    span, summary, points = svc.build_scene_summary(segments)
    assert span is None
    assert summary is None
    assert points == []


def test_very_short_low_content_span_is_honest_empty_state_not_fabricated():
    # "Yes." is real transcript text, but a single content word doesn't
    # clear the meaningful-sentence bar (MIN_CONTENT_WORDS) -- per the
    # approved rule ("a short valid summary is better than a longer
    # nonsense paragraph," and honest empty state over fabrication), this
    # must NOT be padded into a fake-sounding summary. transcript_span_text
    # still reports the real raw text even though summary/key_points don't.
    segments = [_seg("Yes.", id_=1)]
    span, summary, points = svc.build_scene_summary(segments)
    assert span == "Yes."
    assert summary is None
    assert points == []


def test_summary_joins_distinct_sentences_up_to_char_limit():
    # 20 *distinct* long sentences (repeating the same one would all
    # collapse to a single entry via dedup, see
    # test_summary_deduplicates_identical_sentences_across_the_span below)
    # -- this tests the actual join-until-the-limit behavior.
    sentences = [
        f"This is sentence number {i} discussing recursion and base cases in some real detail today."
        for i in range(1, 20)
    ]
    segments = [_seg(" ".join(sentences), id_=1)]
    _span, summary, _points = svc.build_scene_summary(segments)
    assert len(summary) <= svc.SUMMARY_MAX_CHARS
    # Composed only of already-complete cleaned sentences, joined only
    # *between* sentences -- never cut mid-sentence -- so it always ends
    # on real sentence punctuation.
    assert summary.strip().endswith(".")
    assert summary.startswith("This is sentence number 1 ")


def test_summary_deduplicates_identical_sentences_across_the_span():
    # The same complete sentence repeated many times (e.g. a Whisper
    # loop) collapses to one occurrence in both Summary and Key Points --
    # "avoid duplicated consecutive thoughts" / "avoid merely joining
    # every overlapping transcript segment unchanged."
    sentence = "This is a reasonably long sentence about recursion and base cases."
    segments = [_seg(" ".join([sentence] * 20), id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert summary == sentence
    assert points == [sentence]


def test_key_points_deduplicates_and_caps_at_five():
    text = " ".join([f"Point number {i} is real." for i in range(1, 8)] + ["Point number 1 is real."])
    segments = [_seg(text, id_=1)]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert len(points) == svc.KEY_POINTS_MAX
    assert len(set(points)) == len(points)


def test_key_points_drops_filler_only_sentences():
    text = "Um. Recursion needs a base case. Yeah okay. Each call reduces the problem size."
    segments = [_seg(text, id_=1)]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert "Um" not in points
    assert not any(p.lower() in {"um", "yeah okay"} for p in points)
    assert "Recursion needs a base case." in points
    assert "Each call reduces the problem size." in points


def test_key_points_short_clip_returns_fewer_than_cap():
    segments = [_seg("Only one real sentence here.", id_=1)]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert points == ["Only one real sentence here."]


# ===========================================================================
# 1b. Quality-cleanup pipeline (2026-08-06) -- the exact reported bad
# output and every rejection/stripping rule it required
# ===========================================================================


def test_reported_recursion_clip_matches_required_cleanup():
    # The exact real Scene Viewer output reported as low quality:
    # Summary: "iterative solution rather than the recursive one. Okay,
    # so this is the same as I said right now. Recursive algorithms are
    # shorter and easier to understand and to write. Okay, however,"
    # Key Points included "Okay, however," and "Okay, so this is the
    # same as I said right now." as if they were real takeaways.
    segments = [
        _seg("iterative solution rather than the recursive one.", id_=1),
        _seg("Okay, so this is the same as I said right now.", id_=2),
        _seg("Recursive algorithms are shorter and easier to understand and to write.", id_=3),
        _seg("Okay, however,", id_=4),
    ]
    span, summary, points = svc.build_scene_summary(segments)

    # transcript_span_text stays the raw, uncleaned span.
    assert span.startswith("iterative solution")

    # The truncated opening fragment never appears in the cleaned output.
    assert "iterative solution" not in (summary or "")
    assert not any("iterative solution" in p for p in points)

    # Neither filler/meta-reference fragment survives, in either output.
    assert not any(p.strip().lower().startswith("okay") for p in points)
    assert "however" not in (summary or "").lower()

    # The one genuinely meaningful sentence survives, capitalized, as-is.
    assert points == ["Recursive algorithms are shorter and easier to understand and to write."]
    assert summary == "Recursive algorithms are shorter and easier to understand and to write."


def test_dangling_okay_however_is_rejected():
    segments = [_seg("Okay, however,", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == []
    assert summary is None


def test_meta_reference_sentence_is_rejected():
    segments = [_seg("Okay, so this is the same as I said right now.", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == []
    assert summary is None


def test_leading_okay_stripped_when_remainder_is_meaningful():
    segments = [_seg("Okay, recursion needs a base case to terminate properly.", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == ["Recursion needs a base case to terminate properly."]
    assert summary == "Recursion needs a base case to terminate properly."


def test_sentence_ending_in_bare_connector_is_rejected():
    segments = [_seg("This part gets genuinely tricky however,", id_=1)]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert points == []


def test_incomplete_lowercase_opening_fragment_is_rejected():
    # Only the *first* sentence of the whole span is checked this way --
    # see test_lowercase_mid_span_sentence_is_not_rejected below for why
    # a lowercase start elsewhere is treated differently.
    segments = [
        _seg("fragment cut off by the clip window boundary here.", id_=1),
        _seg("This is a complete and useful sentence about the topic.", id_=2),
    ]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert points == ["This is a complete and useful sentence about the topic."]


def test_lowercase_mid_span_sentence_is_not_rejected():
    # A lowercase start *after* the first sentence is Whisper's usual
    # inconsistent capitalization, not a truncation signal -- it must
    # still be evaluated normally, not dropped just for being lowercase.
    segments = [
        _seg("This is the first complete sentence in the span today.", id_=1),
        _seg("recursion also needs a well defined base case to terminate.", id_=2),
    ]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert "This is the first complete sentence in the span today." in points
    assert any(p.lower().startswith("recursion also needs") for p in points)


def test_summary_never_starts_or_ends_on_a_dropped_fragment():
    segments = [
        _seg("iterative solution rather than the recursive one.", id_=1),
        _seg("Recursive algorithms are shorter and easier to write.", id_=2),
        _seg("Okay, however,", id_=3),
    ]
    _span, summary, _points = svc.build_scene_summary(segments)
    assert not summary.lower().startswith("iterative")
    assert not summary.lower().rstrip(".").endswith("however")



# ===========================================================================
# 1c. Informational-usefulness rejection (2026-08-07) -- grammatically
# clean lecturer/student conversational speech still isn't a standalone
# fact, so it must be rejected even though 1b's cleanup already passes it
# ===========================================================================


def test_first_person_conversational_sentence_is_rejected():
    segments = [_seg(
        "I know that currently because recursion is new to you, "
        "you think that the recursive method is harder than the iterative method.",
        id_=1,
    )]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == []
    assert summary is None


def test_context_dependent_conditional_is_rejected():
    segments = [_seg("If that's the case then you will never stop.", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == []
    assert summary is None


def test_as_i_said_instructional_sentence_is_rejected():
    segments = [_seg("As I said before, you can use recursion here.", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == []
    assert summary is None


def test_now_were_going_to_sentence_is_rejected():
    segments = [_seg("Now we're going to see how this works.", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == []
    assert summary is None


def test_useful_technical_sentences_are_accepted():
    for text in [
        "Recursive algorithms are often shorter than equivalent iterative solutions.",
        "A recursive function requires a base case to terminate.",
        "The recursive definition of power reduces the exponent by one at each recursive step.",
    ]:
        segments = [_seg(text, id_=1)]
        _span, summary, points = svc.build_scene_summary(segments)
        assert points == [text], f"expected {text!r} to survive, got {points!r}"
        assert summary == text


def test_legitimate_this_sentence_is_not_rejected():
    # "this" alone must never trigger rejection -- only the exact
    # unresolved-reference phrases ("this one", "this is what", ...) do.
    segments = [_seg("This algorithm uses recursion.", id_=1)]
    _span, summary, points = svc.build_scene_summary(segments)
    assert points == ["This algorithm uses recursion."]
    assert summary == "This algorithm uses recursion."


def test_clip_of_only_conversational_sentences_is_honest_empty_state():
    segments = [
        _seg("I know that currently because recursion is new to you, you think it's harder.", id_=1),
        _seg("If that's the case then you will never stop.", id_=2),
        _seg("Now we're going to see how this works.", id_=3),
    ]
    span, summary, points = svc.build_scene_summary(segments)
    assert span  # raw span still reports the real transcript text
    assert summary is None
    assert points == []


def test_conversational_sentences_followed_by_technical_ones_keep_only_technical():
    segments = [
        _seg("As I said before, you can use recursion here.", id_=1),
        _seg("A recursive function requires a base case to terminate.", id_=2),
        _seg("If that's the case then you will never stop.", id_=3),
        _seg("Recursive algorithms are often shorter than equivalent iterative solutions.", id_=4),
    ]
    span, summary, points = svc.build_scene_summary(segments)
    assert points == [
        "A recursive function requires a base case to terminate.",
        "Recursive algorithms are often shorter than equivalent iterative solutions.",
    ]
    assert "you" not in summary.lower()
    assert "that's the case" not in summary.lower()
    # transcript_span_text stays the raw, unfiltered span -- including the
    # conversational sentences that were dropped from summary/key_points.
    assert "As I said before" in span
    assert "you will never stop" in span


def test_fewer_than_five_useful_statements_is_not_padded():
    segments = [
        _seg("A recursive function requires a base case to terminate.", id_=1),
        _seg("If that's the case then you will never stop.", id_=2),
        _seg("Recursive algorithms are often shorter than equivalent iterative solutions.", id_=3),
    ]
    _span, _summary, points = svc.build_scene_summary(segments)
    assert len(points) == 2
    assert len(points) < svc.KEY_POINTS_MAX


def test_transcript_span_text_remains_raw_and_unchanged_by_new_rules():
    text = "I know that currently because recursion is new to you, you think it's harder."
    segments = [_seg(text, id_=1)]
    span, _summary, _points = svc.build_scene_summary(segments)
    assert span == text


def test_transcript_facts_are_not_rewritten_into_unsupported_claims():
    # Every surviving Key Point must be a substring of the original raw
    # span (after only whitespace/case normalization) -- cleanup may
    # drop or reorder-select sentences, but it must never alter their
    # wording or invent content that wasn't spoken.
    text = "Okay, recursion needs a base case to terminate properly."
    segments = [_seg(text, id_=1)]
    span, _summary, points = svc.build_scene_summary(segments)
    for point in points:
        assert point.lower() in span.lower()


# ===========================================================================
# 2. Database integration (pg_session)
# ===========================================================================


class TestSelectOverlappingSegmentsIntegration:
    def _seed_user_and_video(self, pg_session):
        user = User(
            full_name="Test User", username=f"summaryuser{id(pg_session)}",
            email=f"summaryuser{id(pg_session)}@example.com", password_hash="hash", role=UserRole.USER,
        )
        pg_session.add(user)
        pg_session.flush()
        video = Video(
            owner_id=user.id, title="Integration video", original_filename="int.mp4",
            file_path="videos/x/int.mp4", file_size_bytes=10, mime_type="video/mp4",
            status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
            visibility=MediaVisibility.PRIVATE,
        )
        pg_session.add(video)
        pg_session.flush()
        return user, video

    def test_returns_only_overlapping_segments_in_chronological_order(self, pg_session):
        _user, video = self._seed_user_and_video(pg_session)
        # Clip window: [100, 110)
        before = TranscriptSegment(video_id=video.id, start_time=80.0, end_time=90.0, text="before", source=SubtitleSource.WHISPER)
        overlap_start = TranscriptSegment(video_id=video.id, start_time=95.0, end_time=101.0, text="overlap start", source=SubtitleSource.WHISPER)
        inside = TranscriptSegment(video_id=video.id, start_time=102.0, end_time=105.0, text="inside", source=SubtitleSource.WHISPER)
        overlap_end = TranscriptSegment(video_id=video.id, start_time=109.0, end_time=115.0, text="overlap end", source=SubtitleSource.WHISPER)
        after = TranscriptSegment(video_id=video.id, start_time=120.0, end_time=130.0, text="after", source=SubtitleSource.WHISPER)
        pg_session.add_all([before, overlap_start, inside, overlap_end, after])
        pg_session.flush()

        segments = svc.select_overlapping_segments(pg_session, video.id, 100.0, 110.0)

        assert [s.text for s in segments] == ["overlap start", "inside", "overlap end"]

    def test_touching_but_not_overlapping_boundary_is_excluded(self, pg_session):
        _user, video = self._seed_user_and_video(pg_session)
        # Ends exactly where the window starts -- not an overlap.
        touching_before = TranscriptSegment(video_id=video.id, start_time=90.0, end_time=100.0, text="touching before", source=SubtitleSource.WHISPER)
        # Starts exactly where the window ends -- not an overlap.
        touching_after = TranscriptSegment(video_id=video.id, start_time=110.0, end_time=120.0, text="touching after", source=SubtitleSource.WHISPER)
        pg_session.add_all([touching_before, touching_after])
        pg_session.flush()

        segments = svc.select_overlapping_segments(pg_session, video.id, 100.0, 110.0)

        assert segments == []

    def test_only_the_requested_video_is_returned(self, pg_session):
        _user, video = self._seed_user_and_video(pg_session)
        _user2, other_video = self._seed_user_and_video(pg_session)
        matching = TranscriptSegment(video_id=video.id, start_time=100.0, end_time=105.0, text="mine", source=SubtitleSource.WHISPER)
        other = TranscriptSegment(video_id=other_video.id, start_time=100.0, end_time=105.0, text="not mine", source=SubtitleSource.WHISPER)
        pg_session.add_all([matching, other])
        pg_session.flush()

        segments = svc.select_overlapping_segments(pg_session, video.id, 95.0, 110.0)

        assert [s.text for s in segments] == ["mine"]

    def test_empty_overlap_returns_empty_list(self, pg_session):
        _user, video = self._seed_user_and_video(pg_session)
        segments = svc.select_overlapping_segments(pg_session, video.id, 500.0, 510.0)
        assert segments == []
