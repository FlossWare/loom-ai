"""Conformance tests for SearchBackend implementations.

Any backend that satisfies the SearchBackend protocol should pass all
tests in this module.  Override the ``search_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

from loom_ai import Chunk


async def test_index_and_text_search(search_backend):
    """Indexing a chunk and searching by content finds it."""
    chunk = Chunk(
        id="sc-1",
        document_id="doc-1",
        content="Python programming language",
        chunk_index=0,
    )
    await search_backend.index(chunk, document_title="Python Guide")

    results = await search_backend.text_search("Python", limit=5)
    assert len(results) >= 1
    assert any("Python" in r.content for r in results)


async def test_text_search_no_results(search_backend):
    """Searching for a term that does not exist returns an empty list."""
    results = await search_backend.text_search("zzz_nonexistent_term_zzz")
    assert results == []


async def test_semantic_search_returns_scored_results(search_backend):
    """Semantic search with a stored vector returns scored results."""
    chunk = Chunk(
        id="sem-1",
        document_id="doc-sem",
        content="Machine learning fundamentals",
        chunk_index=0,
    )
    vector = [0.1, 0.2, 0.3, 0.4, 0.5]
    await search_backend.index(chunk, vector, document_title="ML Basics")

    results = await search_backend.semantic_search([0.1, 0.2, 0.3, 0.4, 0.5], limit=5)
    assert len(results) >= 1
    assert all(isinstance(r.score, float) for r in results)


async def test_index_idempotent(search_backend):
    """Re-indexing the same chunk does not create duplicates."""
    chunk = Chunk(
        id="idem-s1",
        document_id="doc-idem",
        content="Idempotent content",
        chunk_index=0,
    )
    first = await search_backend.index(chunk, document_title="Idem")
    second = await search_backend.index(chunk, document_title="Idem")

    assert first is True
    assert second is False  # No new data written

    results = await search_backend.text_search("Idempotent")
    assert len(results) == 1


async def test_delete_by_document(search_backend):
    """delete_by_document removes all indexed chunks for that document."""
    for i in range(3):
        chunk = Chunk(
            id=f"del-c-{i}",
            document_id="del-doc",
            content=f"deletable content {i}",
            chunk_index=i,
        )
        await search_backend.index(chunk, document_title="Del Doc")

    removed = await search_backend.delete_by_document("del-doc")
    assert removed == 3

    results = await search_backend.text_search("deletable content")
    assert results == []


async def test_reindex_with_empty_title_clears_metadata(search_backend):
    """Re-indexing with an empty title must replace the old title (#251)."""
    chunk = Chunk(
        id="stale-1",
        document_id="doc-stale",
        content="stale metadata test",
        chunk_index=0,
    )

    # First index: title is "A"
    await search_backend.index(chunk, document_title="A")
    results = await search_backend.text_search("stale metadata test")
    assert len(results) == 1
    assert results[0].document_title == "A"

    # Re-index with empty title: must clear the title
    changed = await search_backend.index(chunk, document_title="")
    assert changed is True
    results = await search_backend.text_search("stale metadata test")
    assert len(results) == 1
    assert results[0].document_title == ""


async def test_reindex_with_empty_source_clears_metadata(search_backend):
    """Re-indexing with an empty source must replace the old source (#251)."""
    chunk = Chunk(
        id="stale-src-1",
        document_id="doc-stale-src",
        content="stale source test",
        chunk_index=0,
    )

    await search_backend.index(chunk, source="https://example.com")
    results = await search_backend.text_search("stale source test")
    assert len(results) == 1
    assert results[0].source == "https://example.com"

    changed = await search_backend.index(chunk, source="")
    assert changed is True
    results = await search_backend.text_search("stale source test")
    assert len(results) == 1
    assert results[0].source == ""


async def test_reindex_none_preserves_metadata(search_backend):
    """Re-indexing without title/source (None) preserves old values (#251)."""
    chunk = Chunk(
        id="preserve-1",
        document_id="doc-preserve",
        content="preserve metadata test",
        chunk_index=0,
    )

    await search_backend.index(chunk, document_title="Keep Me", source="keep.html")
    results = await search_backend.text_search("preserve metadata test")
    assert len(results) == 1
    assert results[0].document_title == "Keep Me"
    assert results[0].source == "keep.html"

    # Re-index without specifying title/source -- old values must persist
    await search_backend.index(chunk)
    results = await search_backend.text_search("preserve metadata test")
    assert len(results) == 1
    assert results[0].document_title == "Keep Me"
    assert results[0].source == "keep.html"


async def test_hybrid_search(search_backend):
    """Hybrid search combines text and semantic results."""
    chunk = Chunk(
        id="hyb-1",
        document_id="doc-hyb",
        content="Neural network architecture",
        chunk_index=0,
    )
    vector = [0.5, 0.5, 0.5]
    await search_backend.index(chunk, vector, document_title="NN Guide")

    results = await search_backend.hybrid_search("Neural", [0.5, 0.5, 0.5], limit=5)
    assert len(results) >= 1
