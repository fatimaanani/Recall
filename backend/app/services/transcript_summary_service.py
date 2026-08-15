"""Deterministic, non-generative Summary/Key Points for a Scene Viewer clip window. Never invents content: sentences are filtered (discourse filler stripped, fragments/meta-references/first-and-second-person narration rejected) but never rewritten, so a surviving sentence is exactly what the speaker said."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.transcript_segment import TranscriptSegment

SUMMARY_MAX_CHARS = 480

# Upper bound, not a floor; a short or filler-heavy clip may produce fewer than 3, or zero.
KEY_POINTS_MAX = 5

# A sentence needs at least this many content-bearing tokens and characters to count as
# meaningful, catching things like "however" or "okay" surviving alone after prefix stripping.
MIN_CONTENT_WORDS = 3
MIN_SENTENCE_CHARS = 12

# Intentionally a small, conservative list, so a real short sentence is never dropped by mistake.
_FILLER_TOKENS = {
    "um", "uh", "uhh", "umm", "erm", "hmm", "mm", "yeah", "yep", "ok", "okay",
    "right", "so", "well", "like", "you know", "i mean", "alright", "cool", "now",
}

# Used only for the content-word-count check; deliberately generous, so a borderline sentence
# survives rather than being dropped.
_STOPWORDS = _FILLER_TOKENS | {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
    "and", "but", "or", "because", "however", "therefore", "then",
    "of", "to", "in", "on", "at", "for", "with", "as", "if", "not",
    "do", "does", "did", "have", "has", "had", "just", "really", "very",
}

# A sentence ending on a bare connector (e.g. "however,") is a dangling fragment, rejected
# rather than kept as a broken tail.
_TRAILING_CONNECTORS = {"however", "therefore", "because", "and", "but", "so", "then"}

# A sentence that's substantially a reference back to earlier speech rarely carries content on its own.
_META_REFERENCE_PHRASES = [
    "same as i said", "as i said", "like i said", "same as before", "this is the same as",
]

# Word-boundary-matched and case-insensitive, so "we" never matches inside "however" and "us"
# never matches inside "discuss".
_FIRST_PERSON_RE = re.compile(
    r"\b(?:i|i'm|i've|i'll|i'd|me|my|mine|myself|we|we're|we've|we'll|we'd|us|our|ours|ourselves)\b",
    re.IGNORECASE,
)
_SECOND_PERSON_RE = re.compile(
    r"\b(?:you|you're|you've|you'll|you'd|your|yours|yourself|yourselves)\b",
    re.IGNORECASE,
)

# Can't stand alone without the preceding conversation that gave them meaning.
_CONTEXT_DEPENDENT_OPENING_PHRASES = [
    "if that's the case", "if this is the case", "in that case",
    "as i said", "like i said", "as we said", "as mentioned before", "as before",
    "what i mean is", "what i'm saying is",
    "you can see", "as you can see", "remember that",
    "we're going to", "we are going to", "let's", "let us",
    "now we're", "now we are",
]

# Exact phrases only, so a real sentence like "This algorithm uses recursion." is never
# rejected merely for containing "this".
_UNRESOLVED_REFERENCE_PHRASES = [
    "that's the case", "this is what", "that is what", "this one", "that one",
]

_CONTEXT_DEPENDENT_PHRASES = _CONTEXT_DEPENDENT_OPENING_PHRASES + _UNRESOLVED_REFERENCE_PHRASES

# Longest first, so a multi-word phrase is tried before a shorter phrase that's merely its prefix.
_DISCOURSE_LEADING_PHRASES = sorted(
    [
        "okay so", "okay", "so", "well", "right now", "as i said", "like i said",
        "you know", "um", "uh", "uhh", "umm",
    ],
    key=len,
    reverse=True,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_STRIP_RE = re.compile(r"[.!?,;:]+$")
_LEADING_SEP_RE = re.compile(r"^[\s,\-–—:]+")


def select_overlapping_segments(
    db: Session, video_id: int, start_time: float, end_time: float
) -> list[TranscriptSegment]:
    """Every TranscriptSegment for this video overlapping [start_time, end_time), in
    chronological order (half-open interval overlap)."""
    return (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.video_id == video_id,
            TranscriptSegment.start_time < end_time,
            TranscriptSegment.end_time > start_time,
        )
        .order_by(TranscriptSegment.start_time.asc(), TranscriptSegment.id.asc())
        .all()
    )


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


def _normalize_for_comparison(text: str) -> str:
    return _PUNCT_STRIP_RE.sub("", text).strip().lower()


def _combine_segment_texts(segments: list[TranscriptSegment]) -> str:
    """Joins cleaned segment texts, dropping a segment that exactly repeats the immediately
    preceding one (a known Whisper failure mode), but not repeats separated by other content."""
    parts: list[str] = []
    previous_normalized = None
    for segment in segments:
        cleaned = _clean(segment.text)
        if not cleaned:
            continue
        normalized = _normalize_for_comparison(cleaned)
        if normalized and normalized == previous_normalized:
            continue
        parts.append(cleaned)
        previous_normalized = normalized
    return " ".join(parts)


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _is_filler_only(sentence: str) -> bool:
    normalized = _normalize_for_comparison(sentence)
    if not normalized:
        return True
    tokens = normalized.split()
    return all(token in _FILLER_TOKENS for token in tokens)


def _strip_leading_discourse(sentence: str) -> str:
    """Iteratively strips leading discourse/filler phrases; whole-phrase matches only, so "so"
    never matches inside "sole"."""
    text = sentence.strip()
    for _ in range(4):
        lowered = text.lower()
        matched = False
        for phrase in _DISCOURSE_LEADING_PHRASES:
            if not lowered.startswith(phrase):
                continue
            remainder = text[len(phrase):]
            if remainder and remainder[0].isalpha():
                continue
            text = _LEADING_SEP_RE.sub("", remainder)
            matched = True
            break
        if not matched:
            break
    return text.strip()


def _ends_on_bare_connector(sentence: str) -> bool:
    normalized = _normalize_for_comparison(sentence)
    if not normalized:
        return True
    return normalized.split()[-1] in _TRAILING_CONNECTORS


def _contains_meta_reference(sentence: str) -> bool:
    normalized = _normalize_for_comparison(sentence)
    return any(phrase in normalized for phrase in _META_REFERENCE_PHRASES)


def _contains_context_dependent_reference(sentence: str) -> bool:
    normalized = _normalize_for_comparison(sentence)
    return any(phrase in normalized for phrase in _CONTEXT_DEPENDENT_PHRASES)


def _contains_first_person(sentence: str) -> bool:
    return bool(_FIRST_PERSON_RE.search(sentence))


def _contains_second_person(sentence: str) -> bool:
    return bool(_SECOND_PERSON_RE.search(sentence))


def _content_word_count(sentence: str) -> int:
    normalized = _normalize_for_comparison(sentence)
    return sum(1 for token in normalized.split() if token not in _STOPWORDS)


def _capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _clean_sentence(sentence: str) -> str | None:
    """Returns a cleaned/capitalized sentence, or None if it should be rejected; the single place
    every rejection rule lives."""
    stripped = _strip_leading_discourse(sentence)
    if not stripped:
        return None
    if _ends_on_bare_connector(stripped):
        return None
    if _contains_meta_reference(stripped):
        return None
    if _contains_context_dependent_reference(stripped):
        return None
    if _contains_first_person(stripped):
        return None
    if _contains_second_person(stripped):
        return None
    if _is_filler_only(stripped):
        return None
    if len(stripped) < MIN_SENTENCE_CHARS or _content_word_count(stripped) < MIN_CONTENT_WORDS:
        return None
    return _capitalize_first(stripped)


def _join_summary(cleaned_sentences: list[str]) -> str:
    """Joins cleaned sentences up to SUMMARY_MAX_CHARS, cutting only between sentences. The first
    sentence is always included even if it alone exceeds the limit."""
    parts = [cleaned_sentences[0]]
    length = len(parts[0])
    for sentence in cleaned_sentences[1:]:
        new_length = length + 1 + len(sentence)
        if new_length > SUMMARY_MAX_CHARS:
            break
        parts.append(sentence)
        length = new_length
    return " ".join(parts)


def build_scene_summary(
    segments: list[TranscriptSegment],
) -> tuple[str | None, str | None, list[str]]:
    """Returns (transcript_span_text, summary, key_points) for the given overlapping segments.
    transcript_span_text is the raw combined span; summary/key_points come from the cleaned-
    sentence pipeline. Returns summary=None and key_points=[] when nothing survives cleaning,
    rather than a fabricated placeholder."""
    span_text = _combine_segment_texts(segments)
    if not span_text:
        return None, None, []

    raw_sentences = _split_sentences(span_text)
    if not raw_sentences:
        return span_text, None, []

    # Drop a genuinely truncated first fragment; only the very first sentence is checked this
    # way, since a lowercase start mid-span is usually just inconsistent Whisper capitalization.
    start_index = 1 if raw_sentences[0][:1].islower() else 0

    cleaned_sentences: list[str] = []
    seen_normalized: set[str] = set()
    for sentence in raw_sentences[start_index:]:
        cleaned = _clean_sentence(sentence)
        if cleaned is None:
            continue
        normalized = _normalize_for_comparison(cleaned)
        if not normalized or normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        cleaned_sentences.append(cleaned)

    if not cleaned_sentences:
        return span_text, None, []

    key_points = cleaned_sentences[:KEY_POINTS_MAX]
    summary = _join_summary(cleaned_sentences)
    return span_text, summary, key_points
