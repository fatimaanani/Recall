"""
Boundary-cleanup stage between raw time-stamped transcript cues (Whisper
segments or subtitle cues) and the TranscriptSegment rows actually
persisted: merges cues split by near-zero gaps, then splits any cue
still longer than max_duration_seconds.

Word-proportional splitting is used instead of word-level timing because
Whisper only gives segment-level timestamps, so distributing words
evenly by count across equal time windows is the best available
approximation.
"""

from __future__ import annotations

import dataclasses
import math


@dataclasses.dataclass(frozen=True)
class RawCue:
    """One raw time-stamped chunk of transcript text, from any source
    (Whisper segment, uploaded SRT/VTT cue, embedded subtitle cue)."""

    start: float
    end: float
    text: str


@dataclasses.dataclass(frozen=True)
class SegmentedCue:
    """One cleaned-up chunk, ready to become a TranscriptSegment row."""

    start: float
    end: float
    text: str


def segment_cues(
    cues: list[RawCue],
    *,
    merge_gap_seconds: float,
    max_merged_duration_seconds: float,
    max_duration_seconds: float,
) -> list[SegmentedCue]:
    """Runs the merge/split pipeline; safe to call with an empty list."""
    normalized = _normalize_order_and_overlap(cues)
    if not normalized:
        return []
    merged = _merge_short_gaps(normalized, merge_gap_seconds, max_merged_duration_seconds)
    return _split_overlong(merged, max_duration_seconds)


def _normalize_order_and_overlap(cues: list[RawCue]) -> list[RawCue]:
    non_blank = [cue for cue in cues if cue.text.strip()]
    # Stable sort keeps already-ordered cues (the common case) in their original relative order.
    ordered = sorted(non_blank, key=lambda cue: cue.start)

    result: list[RawCue] = []
    previous_end = 0.0
    for cue in ordered:
        start = max(cue.start, previous_end)
        end = max(cue.end, start)  # never reversed: end >= start always
        result.append(RawCue(start=start, end=end, text=cue.text))
        previous_end = end
    return result


def _merge_short_gaps(
    cues: list[RawCue], merge_gap_seconds: float, max_merged_duration_seconds: float
) -> list[RawCue]:
    result: list[RawCue] = []
    current = cues[0]

    for cue in cues[1:]:
        gap = cue.start - current.end
        merged_duration = cue.end - current.start
        if gap <= merge_gap_seconds and merged_duration <= max_merged_duration_seconds:
            current = RawCue(start=current.start, end=cue.end, text=f"{current.text} {cue.text}")
        else:
            result.append(current)
            current = cue
    result.append(current)
    return result


def _split_overlong(cues: list[RawCue], max_duration_seconds: float) -> list[SegmentedCue]:
    result: list[SegmentedCue] = []
    for cue in cues:
        duration = cue.end - cue.start
        if duration <= max_duration_seconds:
            result.append(SegmentedCue(start=cue.start, end=cue.end, text=cue.text))
            continue
        result.extend(_split_one_cue(cue, max_duration_seconds))
    return result


def _split_one_cue(cue: RawCue, max_duration_seconds: float) -> list[SegmentedCue]:
    duration = cue.end - cue.start
    words = cue.text.split()
    # Never split into more parts than there are words, to avoid an empty-text part.
    n_parts = min(math.ceil(duration / max_duration_seconds), len(words))
    n_parts = max(n_parts, 1)

    word_groups = _split_words_evenly(words, n_parts)
    window = duration / n_parts

    parts: list[SegmentedCue] = []
    for index, group_words in enumerate(word_groups):
        part_start = cue.start + index * window
        # Last part gets the exact original end to avoid float drift.
        part_end = cue.end if index == n_parts - 1 else cue.start + (index + 1) * window
        parts.append(SegmentedCue(start=part_start, end=part_end, text=" ".join(group_words)))
    return parts


def _split_words_evenly(words: list[str], n_parts: int) -> list[list[str]]:
    """Distributes `words` into `n_parts` groups as evenly as possible, in
    original order (the first `remainder` groups get one extra word)."""
    base_size, remainder = divmod(len(words), n_parts)
    groups: list[list[str]] = []
    cursor = 0
    for i in range(n_parts):
        size = base_size + (1 if i < remainder else 0)
        groups.append(words[cursor:cursor + size])
        cursor += size
    return groups
