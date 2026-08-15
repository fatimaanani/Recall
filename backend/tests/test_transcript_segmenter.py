"""
test_transcript_segmenter.py

Unit tests for app/processing/transcript_segmenter.py.

1. Shared helpers
2. Chronological order + overlap/reversal repair
3. Blank-cue dropping
4. Merge behavior (gap threshold, max-merged-duration cap)
5. Split behavior (overlong cues, word-proportional distribution)
6. Never-invents-text property (word count/order preserved end to end)
7. Source-preserving passthrough (already-clean input is unchanged)
8. Empty input
"""

from __future__ import annotations

from app.processing.transcript_segmenter import RawCue, SegmentedCue, segment_cues

_DEFAULTS = dict(merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

def _cue(start: float, end: float, text: str) -> RawCue:
    return RawCue(start=start, end=end, text=text)


def _all_words(cues) -> list[str]:
    words: list[str] = []
    for cue in cues:
        words.extend(cue.text.split())
    return words


# ===========================================================================
# 2. Chronological order + overlap/reversal repair
# ===========================================================================

def test_output_is_chronologically_ordered_even_if_input_is_not():
    cues = [_cue(5.0, 6.0, "second"), _cue(0.0, 1.0, "first")]
    out = segment_cues(cues, **_DEFAULTS)
    starts = [c.start for c in out]
    assert starts == sorted(starts)


def test_overlapping_cues_are_resolved_to_non_overlapping():
    cues = [_cue(0.0, 5.0, "first"), _cue(3.0, 8.0, "second")]
    out = segment_cues(cues, **_DEFAULTS)
    for a, b in zip(out, out[1:]):
        assert a.end <= b.start


def test_reversed_cue_is_clamped_not_swapped():
    # end < start is a malformed input -- must never be "fixed" by
    # swapping (that would silently relocate the text to a different
    # time), only clamped to a zero-duration point.
    cues = [_cue(5.0, 2.0, "reversed")]
    out = segment_cues(cues, **_DEFAULTS)
    assert len(out) == 1
    assert out[0].start == 5.0
    assert out[0].end == 5.0
    assert out[0].text == "reversed"


def test_no_two_output_cues_overlap_across_a_larger_batch():
    cues = [
        _cue(10.0, 20.0, "a"),
        _cue(0.0, 5.0, "b"),
        _cue(4.0, 12.0, "c"),
        _cue(19.0, 25.0, "d"),
    ]
    out = segment_cues(cues, **_DEFAULTS)
    for a, b in zip(out, out[1:]):
        assert a.end <= b.start
        assert a.start <= a.end


# ===========================================================================
# 3. Blank-cue dropping
# ===========================================================================

def test_blank_text_cues_are_dropped():
    cues = [_cue(0.0, 1.0, "hello"), _cue(1.0, 2.0, "   "), _cue(2.0, 3.0, "world")]
    out = segment_cues(cues, **_DEFAULTS)
    assert all(c.text.strip() for c in out)
    assert _all_words(out) == ["hello", "world"]


def test_all_blank_input_returns_empty_list():
    cues = [_cue(0.0, 1.0, ""), _cue(1.0, 2.0, "   ")]
    assert segment_cues(cues, **_DEFAULTS) == []


# ===========================================================================
# 4. Merge behavior
# ===========================================================================

def test_cues_within_merge_gap_are_combined_with_a_single_space():
    cues = [_cue(0.0, 1.0, "hello"), _cue(1.2, 2.0, "world")]
    out = segment_cues(cues, merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)
    assert len(out) == 1
    assert out[0].text == "hello world"
    assert out[0].start == 0.0
    assert out[0].end == 2.0


def test_cues_beyond_merge_gap_are_not_combined():
    cues = [_cue(0.0, 1.0, "hello"), _cue(3.0, 4.0, "world")]
    out = segment_cues(cues, merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)
    assert len(out) == 2
    assert [c.text for c in out] == ["hello", "world"]


def test_merge_respects_max_merged_duration_cap():
    # Gap is well within the merge threshold, but merging would produce a
    # 20s segment against a 5s cap -- must stay split.
    cues = [_cue(0.0, 10.0, "first"), _cue(10.2, 20.0, "second")]
    out = segment_cues(cues, merge_gap_seconds=0.5, max_merged_duration_seconds=5.0, max_duration_seconds=30.0)
    assert len(out) == 2


def test_merge_chains_across_more_than_two_short_fragments():
    cues = [
        _cue(0.0, 1.0, "one"),
        _cue(1.1, 2.0, "two"),
        _cue(2.1, 3.0, "three"),
    ]
    out = segment_cues(cues, merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)
    assert len(out) == 1
    assert out[0].text == "one two three"
    assert out[0].start == 0.0
    assert out[0].end == 3.0


# ===========================================================================
# 5. Split behavior
# ===========================================================================

def test_overlong_cue_is_split_into_multiple_time_windows():
    cue = _cue(0.0, 40.0, "one two three four five six seven eight")
    out = segment_cues([cue], merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=20.0)
    assert len(out) == 2
    assert out[0].start == 0.0
    assert out[1].end == 40.0
    # Contiguous, non-overlapping windows covering the full original range.
    assert out[0].end == out[1].start


def test_split_never_produces_more_parts_than_words():
    # Duration implies 4 parts (100s / 30s -> ceil = 4), but only 2 words
    # exist -- must clamp to 2 parts, never an empty-text part.
    cue = _cue(0.0, 100.0, "alpha beta")
    out = segment_cues([cue], merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)
    assert len(out) == 2
    assert all(c.text.strip() for c in out)


def test_split_parts_are_in_chronological_order_and_contiguous():
    cue = _cue(100.0, 190.0, " ".join(f"w{i}" for i in range(12)))
    out = segment_cues([cue], merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)
    for a, b in zip(out, out[1:]):
        assert a.end == b.start
    assert out[0].start == 100.0
    assert out[-1].end == 190.0


def test_cue_within_max_duration_is_never_split():
    cue = _cue(0.0, 10.0, "a short segment")
    out = segment_cues([cue], **_DEFAULTS)
    assert len(out) == 1
    assert out[0].text == "a short segment"


# ===========================================================================
# 6. Never-invents-text property
# ===========================================================================

def test_word_count_and_order_are_preserved_end_to_end():
    cues = [
        _cue(0.0, 1.0, "the quick brown"),
        _cue(1.05, 2.0, "fox jumps"),
        _cue(50.0, 90.0, " ".join(f"word{i}" for i in range(20))),  # forces a split
        _cue(200.0, 200.5, "  "),  # blank -- must be dropped, not counted
    ]
    original_words = []
    for cue in cues:
        original_words.extend(cue.text.split())

    out = segment_cues(cues, merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=20.0)
    assert _all_words(out) == original_words


def test_large_random_batch_never_loses_or_duplicates_a_word():
    import random

    rng = random.Random(42)
    cues = []
    t = 0.0
    all_words: list[str] = []
    for i in range(50):
        gap = rng.choice([0.05, 0.2, 0.6, 2.0, 5.0])
        t += gap
        duration = rng.choice([0.5, 1.0, 3.0, 45.0])
        text_words = [f"w{i}_{j}" for j in range(rng.randint(1, 6))]
        cues.append(_cue(t, t + duration, " ".join(text_words)))
        all_words.extend(text_words)
        t += duration

    out = segment_cues(cues, merge_gap_seconds=0.5, max_merged_duration_seconds=15.0, max_duration_seconds=30.0)
    assert _all_words(out) == all_words


# ===========================================================================
# 7. Source-preserving passthrough
# ===========================================================================

def test_already_clean_input_passes_through_unchanged():
    cues = [
        _cue(0.0, 5.0, "hello there"),
        _cue(10.0, 15.0, "a completely separate sentence"),
    ]
    out = segment_cues(cues, **_DEFAULTS)
    assert out == [
        SegmentedCue(start=0.0, end=5.0, text="hello there"),
        SegmentedCue(start=10.0, end=15.0, text="a completely separate sentence"),
    ]


# ===========================================================================
# 8. Empty input
# ===========================================================================

def test_empty_input_returns_empty_list():
    assert segment_cues([], **_DEFAULTS) == []
