"""
test_embedding_processor.py -- unit tests, no PostgreSQL required.

1. Dimension + shape
2. Batch encoding (one call, not one per segment)
3. Failure wrapping
4. Model caching (lazy singleton)
"""

from __future__ import annotations

import numpy as np
import pytest

from app.processing import embedding_processor
from app.processing.ffmpeg_processor import ProcessingError


@pytest.fixture(autouse=True)
def _reset_model_cache():
    # _model is a module-level singleton; reset it around every test so a
    # mock installed by one test can't leak into the next.
    embedding_processor._model = None
    yield
    embedding_processor._model = None


class _FakeSentenceTransformer:
    """Stands in for the real SentenceTransformer -- returns deterministic
    zero-vectors of the configured dimension without needing the actual
    (large, network-downloaded) model."""

    def __init__(self, vector_dim: int = 384):
        self.vector_dim = vector_dim
        self.calls: list[dict] = []

    def encode(self, texts, batch_size=None, show_progress_bar=None, convert_to_numpy=None):
        self.calls.append({"texts": list(texts), "batch_size": batch_size})
        return np.zeros((len(texts), self.vector_dim), dtype="float32")


# Dimension + shape
def test_generate_embeddings_returns_384_dim_vectors(mocker):
    fake_model = _FakeSentenceTransformer()
    mocker.patch.object(embedding_processor, "_get_model", return_value=fake_model)

    vectors = embedding_processor.generate_embeddings(["hello world", "a second segment"])

    assert len(vectors) == 2
    assert all(len(vector) == 384 for vector in vectors)
    assert all(isinstance(vector, list) for vector in vectors)  # tolist(), not a numpy array


def test_generate_embeddings_empty_list_returns_empty_without_calling_model(mocker):
    get_model_spy = mocker.patch.object(embedding_processor, "_get_model")

    result = embedding_processor.generate_embeddings([])

    assert result == []
    get_model_spy.assert_not_called()


# Batch encoding (one call, not one per segment)
def test_generate_embeddings_batches_in_a_single_encode_call(mocker):
    fake_model = _FakeSentenceTransformer()
    mocker.patch.object(embedding_processor, "_get_model", return_value=fake_model)

    texts = [f"segment {i}" for i in range(10)]
    embedding_processor.generate_embeddings(texts)

    assert len(fake_model.calls) == 1
    assert fake_model.calls[0]["texts"] == texts


# Failure wrapping
def test_generate_embeddings_wraps_model_failure_as_processing_error(mocker):
    class _FailingModel:
        def encode(self, *args, **kwargs):
            raise RuntimeError("out of memory")

    mocker.patch.object(embedding_processor, "_get_model", return_value=_FailingModel())

    with pytest.raises(ProcessingError):
        embedding_processor.generate_embeddings(["will fail"])


# Model caching (lazy singleton)
def test_get_model_is_loaded_once_and_cached(mocker):
    fake_model = _FakeSentenceTransformer()
    mock_constructor = mocker.patch("sentence_transformers.SentenceTransformer", return_value=fake_model)

    first = embedding_processor._get_model()
    second = embedding_processor._get_model()

    assert first is second
    mock_constructor.assert_called_once()
