"""Property-based fuzz tests for SearchBackend (MemorySearchBackend).

Uses Hypothesis to generate edge-case inputs and verifies that search
operations never crash with valid-typed but unusual inputs, maintain
idempotent indexing, and handle concurrent mutations without corruption.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from loom_ai.backends.memory import MemorySearchBackend
from loom_ai.models import Chunk


def _run(coro):
    return asyncio.run(coro)


FUZZ_TEXT = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "M", "N", "P", "S", "Z")),
    min_size=0,
    max_size=5000,
)

FUZZ_ID = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
)

FUZZ_VECTOR = st.lists(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    min_size=3,
    max_size=16,
)


class TestSearchFuzz:
    @given(
        chunk_id=FUZZ_ID,
        doc_id=FUZZ_ID,
        content=FUZZ_TEXT,
        title=FUZZ_TEXT,
        source=FUZZ_TEXT,
    )
    @settings(max_examples=100, deadline=None)
    def test_index_never_crashes(self, chunk_id, doc_id, content, title, source):
        backend = MemorySearchBackend()
        chunk = Chunk(id=chunk_id, document_id=doc_id, content=content, chunk_index=0)
        result = _run(backend.index(chunk, document_title=title, source=source))
        assert isinstance(result, bool)

    @given(chunk_id=FUZZ_ID, doc_id=FUZZ_ID, content=FUZZ_TEXT)
    @settings(max_examples=50, deadline=None)
    def test_index_is_idempotent(self, chunk_id, doc_id, content):
        backend = MemorySearchBackend()
        chunk = Chunk(id=chunk_id, document_id=doc_id, content=content, chunk_index=0)
        first = _run(backend.index(chunk, document_title="T"))
        second = _run(backend.index(chunk, document_title="T"))
        assert first is True
        assert second is False

    @given(query=FUZZ_TEXT, limit=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_text_search_on_empty_backend(self, query, limit):
        backend = MemorySearchBackend()
        results = _run(backend.text_search(query, limit=limit))
        assert results == []

    @given(
        content=st.text(min_size=5, max_size=500),
        query=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50, deadline=None)
    def test_text_search_finds_indexed_content(self, content, query):
        backend = MemorySearchBackend()
        chunk = Chunk(id="s-1", document_id="d-1", content=content, chunk_index=0)
        _run(backend.index(chunk))

        results = _run(backend.text_search(query))
        if query.lower() in content.lower():
            assert len(results) >= 1
        else:
            assert isinstance(results, list)

    @given(vector=FUZZ_VECTOR)
    @settings(max_examples=50, deadline=None)
    def test_semantic_search_on_empty_backend(self, vector):
        backend = MemorySearchBackend()
        results = _run(backend.semantic_search(vector))
        assert results == []

    @given(
        vector=FUZZ_VECTOR,
        content=FUZZ_TEXT,
    )
    @settings(max_examples=50, deadline=None)
    def test_semantic_search_with_indexed_vector(self, vector, content):
        backend = MemorySearchBackend()
        chunk = Chunk(id="sv-1", document_id="d-1", content=content, chunk_index=0)
        _run(backend.index(chunk, vector))

        results = _run(backend.semantic_search(vector))
        assert len(results) >= 1
        assert all(isinstance(r.score, float) for r in results)

    @given(
        query=FUZZ_TEXT,
        vector=FUZZ_VECTOR,
        text_weight=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=50, deadline=None)
    def test_hybrid_search_never_crashes(self, query, vector, text_weight):
        backend = MemorySearchBackend()
        chunk = Chunk(id="h-1", document_id="d-1", content="sample text", chunk_index=0)
        _run(backend.index(chunk, vector))

        results = _run(backend.hybrid_search(query, vector, text_weight=text_weight))
        assert isinstance(results, list)

    @given(doc_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_delete_by_document_on_empty_backend(self, doc_id):
        backend = MemorySearchBackend()
        removed = _run(backend.delete_by_document(doc_id))
        assert removed == 0

    @given(doc_id=FUZZ_ID, n=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_delete_by_document_removes_all(self, doc_id, n):
        backend = MemorySearchBackend()
        for i in range(n):
            chunk = Chunk(
                id=f"dbd-{i}", document_id=doc_id, content=f"body {i}", chunk_index=i
            )
            _run(backend.index(chunk))

        removed = _run(backend.delete_by_document(doc_id))
        assert removed == n

    @given(
        chunk_id=FUZZ_ID,
        content_v1=st.text(min_size=1, max_size=200),
        content_v2=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=50, deadline=None)
    def test_reindex_with_new_content_replaces(self, chunk_id, content_v1, content_v2):
        backend = MemorySearchBackend()
        c1 = Chunk(id=chunk_id, document_id="d", content=content_v1, chunk_index=0)
        c2 = Chunk(id=chunk_id, document_id="d", content=content_v2, chunk_index=0)

        _run(backend.index(c1))
        _run(backend.index(c2))

        results = _run(backend.text_search(content_v2))
        matching = [r for r in results if r.chunk_id == chunk_id]
        if content_v2.lower() in content_v2.lower() and content_v2:
            for r in matching:
                assert r.content == content_v2


class TestSearchConcurrency:
    async def test_concurrent_index_no_corruption(self):
        backend = MemorySearchBackend()
        chunks = [
            Chunk(id=f"ci-{i}", document_id="d", content=f"chunk {i}", chunk_index=i)
            for i in range(50)
        ]

        await asyncio.gather(*(backend.index(c) for c in chunks))

        results = await backend.text_search("chunk", limit=100)
        assert len(results) == 50

    async def test_concurrent_index_and_delete(self):
        backend = MemorySearchBackend()
        for i in range(20):
            chunk = Chunk(
                id=f"cid-{i}", document_id="doc-a", content=f"a-{i}", chunk_index=i
            )
            await backend.index(chunk)

        async def index_more():
            for i in range(20):
                chunk = Chunk(
                    id=f"cid-new-{i}",
                    document_id="doc-b",
                    content=f"b-{i}",
                    chunk_index=i,
                )
                await backend.index(chunk)

        async def delete_doc_a():
            await backend.delete_by_document("doc-a")

        await asyncio.gather(index_more(), delete_doc_a())

        remaining_a = await backend.text_search("a-")
        remaining_a = [
            r
            for r in remaining_a
            if r.chunk_id.startswith("cid-") and not r.chunk_id.startswith("cid-new")
        ]
        assert len(remaining_a) == 0
