"""Conformance tests for EmbeddingBackend implementations.

Any backend that satisfies the EmbeddingBackend protocol should pass all
tests in this module.  Override the ``embedding_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations


async def test_embed_text_returns_vector(embedding_backend):
    """Embedding a single text returns a non-empty vector."""
    vectors = await embedding_backend.embed(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0
    assert all(isinstance(v, float) for v in vectors[0])


async def test_embed_single_returns_vector(embedding_backend):
    """embed_single returns a vector for one text."""
    vector = await embedding_backend.embed_single("test input")
    assert len(vector) > 0
    assert all(isinstance(v, float) for v in vector)


async def test_vector_has_consistent_dimensions(embedding_backend):
    """All vectors from the same model have the same dimensionality."""
    v1 = await embedding_backend.embed_single("first")
    v2 = await embedding_backend.embed_single("second")
    assert len(v1) == len(v2)

    dims = await embedding_backend.dimensions()
    assert len(v1) == dims


async def test_multiple_texts_return_multiple_vectors(embedding_backend):
    """Embedding multiple texts returns one vector per input."""
    texts = ["alpha", "bravo", "charlie"]
    vectors = await embedding_backend.embed(texts)
    assert len(vectors) == 3
    # All vectors should have the same dimension
    dims = {len(v) for v in vectors}
    assert len(dims) == 1


async def test_available_models(embedding_backend):
    """available_models returns at least one model identifier."""
    models = await embedding_backend.available_models()
    assert len(models) >= 1
    assert all(isinstance(m, str) for m in models)
