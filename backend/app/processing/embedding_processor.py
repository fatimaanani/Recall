from __future__ import annotations

import logging
import threading

from app.config import get_settings
from app.processing.ffmpeg_processor import ProcessingError

settings = get_settings()
logger = logging.getLogger(__name__)

# Unlike Whisper, which reloads its model fresh in a new subprocess per
# call, the embedding model is loaded once per process and reused, so this
# lock guards both the lazy load and each encode() call.
_model_lock = threading.Lock()
_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        # Re-check in case another thread loaded the model while this one waited.
        if _model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ProcessingError(
                    "sentence-transformers is not installed -- add it to requirements.txt "
                    "and pip install."
                ) from exc
            logger.info(
                "Loading embedding model %s on %s (first use this process)...",
                settings.embedding_model_name, settings.embedding_device,
            )
            _model = SentenceTransformer(settings.embedding_model_name, device=settings.embedding_device)
        return _model


# Called once per video with all of its segments' text, since
# sentence-transformers batches internally far more efficiently than a loop
# of single calls.
def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = _get_model()
    with _model_lock:
        try:
            vectors = model.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:  # noqa: BLE001, reported to the caller as ProcessingError
            raise ProcessingError(f"Embedding generation failed: {exc}") from exc

    # pgvector's SQLAlchemy Vector column takes a plain list of floats, not a numpy array.
    return [vector.tolist() for vector in vectors]
