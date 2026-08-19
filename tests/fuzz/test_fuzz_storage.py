"""Property-based fuzz tests for StorageBackend (MemoryStorageBackend).

Uses Hypothesis to generate edge-case inputs -- empty strings, unicode,
very long strings, special characters -- and verifies that no operation
crashes with valid-typed but unusual inputs.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from loom_ai.backends.memory import MemoryStorageBackend
from loom_ai.models import Chunk, Document, Embedding


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


class TestStorageFuzz:
    @given(doc_id=FUZZ_ID, title=FUZZ_TEXT, content=FUZZ_TEXT)
    @settings(max_examples=100, deadline=None)
    def test_store_and_retrieve_never_crashes(self, doc_id, title, content):
        backend = MemoryStorageBackend()
        doc = Document(id=doc_id, title=title, content=content)
        result_id = _run(backend.store_document(doc))
        assert result_id == doc_id

        retrieved = _run(backend.get_document(doc_id))
        assert retrieved is not None
        assert retrieved.title == title
        assert retrieved.content == content

    @given(doc_id=FUZZ_ID, title=FUZZ_TEXT, content=FUZZ_TEXT)
    @settings(max_examples=50, deadline=None)
    def test_store_is_idempotent(self, doc_id, title, content):
        backend = MemoryStorageBackend()
        doc = Document(id=doc_id, title=title, content=content)
        _run(backend.store_document(doc))
        _run(backend.store_document(doc))

        assert _run(backend.count_documents()) == 1

    @given(doc_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_get_missing_returns_none(self, doc_id):
        backend = MemoryStorageBackend()
        assert _run(backend.get_document(doc_id)) is None

    @given(doc_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_delete_missing_returns_false(self, doc_id):
        backend = MemoryStorageBackend()
        assert _run(backend.delete_document(doc_id)) is False

    @given(doc_id=FUZZ_ID, title=FUZZ_TEXT, content=FUZZ_TEXT)
    @settings(max_examples=50, deadline=None)
    def test_store_delete_roundtrip(self, doc_id, title, content):
        backend = MemoryStorageBackend()
        doc = Document(id=doc_id, title=title, content=content)
        _run(backend.store_document(doc))
        deleted = _run(backend.delete_document(doc_id))
        assert deleted is True
        assert _run(backend.get_document(doc_id)) is None
        assert _run(backend.count_documents()) == 0

    @given(
        doc_id=FUZZ_ID,
        chunk_id=FUZZ_ID,
        chunk_content=FUZZ_TEXT,
        chunk_index=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=50, deadline=None)
    def test_store_and_retrieve_chunks(
        self, doc_id, chunk_id, chunk_content, chunk_index
    ):
        backend = MemoryStorageBackend()
        doc = Document(id=doc_id, title="t", content="c")
        _run(backend.store_document(doc))

        chunk = Chunk(
            id=chunk_id,
            document_id=doc_id,
            content=chunk_content,
            chunk_index=chunk_index,
        )
        stored = _run(backend.store_chunks(doc_id, [chunk]))
        assert stored == 1

        retrieved = _run(backend.get_chunks(doc_id))
        assert len(retrieved) == 1
        assert retrieved[0].content == chunk_content

    @given(
        emb_id=FUZZ_ID,
        chunk_id=FUZZ_ID,
        vector=st.lists(
            st.floats(allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=16,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_store_embeddings_never_crashes(self, emb_id, chunk_id, vector):
        backend = MemoryStorageBackend()
        emb = Embedding(id=emb_id, chunk_id=chunk_id, vector=vector)
        count = _run(backend.store_embeddings([emb]))
        assert count == 1
        assert _run(backend.count_embeddings()) == 1

    @given(
        limit=st.integers(min_value=0, max_value=1000),
        offset=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=50, deadline=None)
    def test_list_documents_with_arbitrary_pagination(self, limit, offset):
        backend = MemoryStorageBackend()
        for i in range(5):
            _run(backend.store_document(Document(id=f"d-{i}", title="t", content="c")))

        result = _run(backend.list_documents(limit=limit, offset=offset))
        assert isinstance(result, list)
        assert len(result) <= max(limit, 0)


class TestStorageConcurrency:
    async def test_concurrent_stores_do_not_corrupt(self):
        backend = MemoryStorageBackend()
        docs = [
            Document(id=f"conc-{i}", title=f"T{i}", content=f"C{i}") for i in range(50)
        ]

        await asyncio.gather(*(backend.store_document(d) for d in docs))

        assert await backend.count_documents() == 50
        for i in range(50):
            retrieved = await backend.get_document(f"conc-{i}")
            assert retrieved is not None

    async def test_concurrent_store_and_delete(self):
        backend = MemoryStorageBackend()
        for i in range(20):
            await backend.store_document(Document(id=f"cd-{i}", title="t", content="c"))

        async def store_more():
            for i in range(20, 40):
                await backend.store_document(
                    Document(id=f"cd-{i}", title="t", content="c")
                )

        async def delete_some():
            for i in range(10):
                await backend.delete_document(f"cd-{i}")

        await asyncio.gather(store_more(), delete_some())

        remaining = await backend.count_documents()
        assert remaining >= 20
