"""Tests for PostgreSQL backend implementations (issue #4).

All tests use mocks -- no running PostgreSQL instance required.
The asyncpg pool is faked with an ``AsyncMock`` so that each backend
class can be exercised against deterministic query results.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from loom_ai.models import Chunk, Document, Embedding
from loom_ai.models_phase1 import RetrievalResult

# Guard: skip the whole module if asyncpg is not importable at test
# time (e.g. CI without the postgresql extra).  The import guard in
# the backend module itself handles the runtime case.
pytest.importorskip(
    "loom_ai.backends.postgresql",
    reason="PostgreSQL backend not importable (asyncpg may be missing)",
)

from loom_ai.backends.postgresql import (  # noqa: E402
    PostgresqlKnowledgeStore,
    PostgresqlPersistentMemory,
    PostgresqlSearchBackend,
    PostgresqlSecretsBackend,
    PostgresqlStorageBackend,
    _require_asyncpg,
)

# ── Fixtures ────────────────────────────────────────────────────────────


def _make_pool():
    """Build a mock asyncpg pool with acquire() as async context manager."""
    pool = MagicMock()
    conn = AsyncMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool, conn


@pytest.fixture
def pool_conn():
    """Return ``(pool, conn)`` mock pair."""
    return _make_pool()


# ── _require_asyncpg ────────────────────────────────────────────────────


def test_require_asyncpg_no_error():
    """Should not raise when asyncpg is available."""
    _require_asyncpg()


# ── PostgresqlStorageBackend ────────────────────────────────────────────


class TestPostgresqlStorageBackend:
    """Unit tests for document / chunk / embedding persistence."""

    async def test_store_document(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        backend = PostgresqlStorageBackend(pool)

        doc = Document(id="d1", title="Test", content="Hello", url="u", category="c")
        result = await backend.store_document(doc)

        assert result == "d1"
        conn.execute.assert_awaited_once()

    async def test_get_document_found(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(
            return_value={
                "id": "d1",
                "title": "Test",
                "content": "Hello",
                "url": "",
                "category": "",
                "metadata": "{}",
                "created_at": "2025-01-01",
            }
        )
        backend = PostgresqlStorageBackend(pool)
        doc = await backend.get_document("d1")

        assert doc is not None
        assert doc.id == "d1"
        assert doc.title == "Test"

    async def test_get_document_not_found(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value=None)
        backend = PostgresqlStorageBackend(pool)

        assert await backend.get_document("missing") is None

    async def test_list_documents(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "d1",
                    "title": "A",
                    "content": "a",
                    "url": "",
                    "category": "",
                    "metadata": "{}",
                    "created_at": "",
                },
            ]
        )
        backend = PostgresqlStorageBackend(pool)
        docs = await backend.list_documents(limit=10, offset=0)
        assert len(docs) == 1
        assert docs[0].id == "d1"

    async def test_delete_document(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 1")
        backend = PostgresqlStorageBackend(pool)

        assert await backend.delete_document("d1") is True

    async def test_delete_document_not_found(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 0")
        backend = PostgresqlStorageBackend(pool)

        assert await backend.delete_document("missing") is False

    async def test_count_documents(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchval = AsyncMock(return_value=42)
        backend = PostgresqlStorageBackend(pool)

        assert await backend.count_documents() == 42

    async def test_store_chunks(self, pool_conn):
        pool, conn = pool_conn
        conn.executemany = AsyncMock()
        backend = PostgresqlStorageBackend(pool)

        chunks = [
            Chunk(id="c1", document_id="d1", content="a", chunk_index=0),
            Chunk(id="c2", document_id="d1", content="b", chunk_index=1),
        ]
        count = await backend.store_chunks("d1", chunks)
        assert count == 2

    async def test_store_chunks_empty(self, pool_conn):
        pool, conn = pool_conn
        backend = PostgresqlStorageBackend(pool)
        assert await backend.store_chunks("d1", []) == 0

    async def test_get_chunks(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "c1",
                    "document_id": "d1",
                    "content": "hello",
                    "chunk_index": 0,
                    "content_hash": "",
                },
            ]
        )
        backend = PostgresqlStorageBackend(pool)
        chunks = await backend.get_chunks("d1")
        assert len(chunks) == 1
        assert chunks[0].id == "c1"

    async def test_get_chunks_batch_empty(self, pool_conn):
        pool, conn = pool_conn
        backend = PostgresqlStorageBackend(pool)
        assert await backend.get_chunks_batch([]) == []

    async def test_count_chunks(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchval = AsyncMock(return_value=10)
        backend = PostgresqlStorageBackend(pool)
        assert await backend.count_chunks() == 10

    async def test_store_embeddings(self, pool_conn):
        pool, conn = pool_conn
        conn.executemany = AsyncMock()
        backend = PostgresqlStorageBackend(pool)

        embs = [
            Embedding(id="e1", chunk_id="c1", vector=[0.1, 0.2]),
        ]
        assert await backend.store_embeddings(embs) == 1

    async def test_store_embeddings_empty(self, pool_conn):
        pool, conn = pool_conn
        backend = PostgresqlStorageBackend(pool)
        assert await backend.store_embeddings([]) == 0

    async def test_count_embeddings(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchval = AsyncMock(return_value=5)
        backend = PostgresqlStorageBackend(pool)
        assert await backend.count_embeddings() == 5

    async def test_delete_chunks(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 3")
        backend = PostgresqlStorageBackend(pool)
        assert await backend.delete_chunks("d1") is True

    async def test_delete_chunks_none(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 0")
        backend = PostgresqlStorageBackend(pool)
        assert await backend.delete_chunks("d1") is False

    async def test_get_pending_chunks_no_cursor(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "c1",
                    "document_id": "d1",
                    "content": "x",
                    "chunk_index": 0,
                    "content_hash": "",
                },
            ]
        )
        backend = PostgresqlStorageBackend(pool)
        result = await backend.get_pending_chunks(10)
        assert len(result) == 1

    async def test_get_pending_chunks_with_cursor(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(return_value=[])
        backend = PostgresqlStorageBackend(pool)
        result = await backend.get_pending_chunks(10, after_id="c0")
        assert result == []


# ── PostgresqlSecretsBackend ────────────────────────────────────────────


class TestPostgresqlSecretsBackend:
    """Unit tests for secret key-value storage."""

    async def test_get_found(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchval = AsyncMock(return_value="secret-value")
        backend = PostgresqlSecretsBackend(pool)
        assert await backend.get("api-key") == "secret-value"

    async def test_get_missing(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchval = AsyncMock(return_value=None)
        backend = PostgresqlSecretsBackend(pool)
        assert await backend.get("missing") is None

    async def test_set(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        backend = PostgresqlSecretsBackend(pool)
        assert await backend.set("key", "val") is True

    async def test_list_names(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(return_value=[{"name": "a"}, {"name": "b"}])
        backend = PostgresqlSecretsBackend(pool)
        names = await backend.list_names()
        assert names == ["a", "b"]

    async def test_delete_found(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 1")
        backend = PostgresqlSecretsBackend(pool)
        assert await backend.delete("key") is True

    async def test_delete_missing(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 0")
        backend = PostgresqlSecretsBackend(pool)
        assert await backend.delete("missing") is False


# ── PostgresqlSearchBackend ─────────────────────────────────────────────


class TestPostgresqlSearchBackend:
    """Unit tests for full-text and semantic search."""

    async def test_text_search(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "chunk_id": "c1",
                    "content": "hello world",
                    "document_title": "Doc",
                    "source": "s",
                    "score": 0.5,
                },
            ]
        )
        backend = PostgresqlSearchBackend(pool)
        results = await backend.text_search("hello")
        assert len(results) == 1
        assert results[0].chunk_id == "c1"
        assert results[0].score == 0.5

    async def test_semantic_search(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "chunk_id": "c2",
                    "content": "similar text",
                    "document_title": "",
                    "source": "",
                    "score": 0.9,
                },
            ]
        )
        backend = PostgresqlSearchBackend(pool)
        results = await backend.semantic_search([0.1, 0.2, 0.3])
        assert len(results) == 1
        assert results[0].score == 0.9

    async def test_delete_by_document(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 3")
        backend = PostgresqlSearchBackend(pool)
        assert await backend.delete_by_document("d1") == 3

    async def test_delete_by_document_zero(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 0")
        backend = PostgresqlSearchBackend(pool)
        assert await backend.delete_by_document("d1") == 0

    async def test_hybrid_search(self, pool_conn):
        pool, conn = pool_conn
        # text_search and semantic_search both call conn.fetch.
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "chunk_id": "c1",
                    "content": "text",
                    "document_title": "",
                    "source": "",
                    "score": 0.8,
                },
            ]
        )
        backend = PostgresqlSearchBackend(pool)
        results = await backend.hybrid_search("query", [0.1, 0.2])
        assert len(results) >= 1


# ── PostgresqlPersistentMemory ──────────────────────────────────────────


class TestPostgresqlPersistentMemory:
    """Unit tests for named memory store."""

    async def test_store(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        mem = PostgresqlPersistentMemory(pool)

        record_id = await mem.store("greeting", "Hello!", memory_type="fact")
        assert isinstance(record_id, str)
        assert len(record_id) > 0
        conn.execute.assert_awaited_once()

    async def test_recall_found(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(
            return_value={
                "id": "r1",
                "name": "greeting",
                "content": "Hello!",
                "memory_type": "fact",
                "metadata": '{"source": "test"}',
                "created_at": "2025-01-01",
                "updated_at": "2025-01-01",
            }
        )
        mem = PostgresqlPersistentMemory(pool)
        record = await mem.recall("greeting")

        assert record is not None
        assert record.id == "r1"
        assert record.name == "greeting"
        assert record.content == "Hello!"
        assert record.metadata == {"source": "test"}

    async def test_recall_missing(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value=None)
        mem = PostgresqlPersistentMemory(pool)
        assert await mem.recall("nonexistent") is None

    async def test_search(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "r1",
                    "name": "py-info",
                    "content": "Python info",
                    "memory_type": "fact",
                    "metadata": "{}",
                    "created_at": "",
                    "updated_at": "",
                },
            ]
        )
        mem = PostgresqlPersistentMemory(pool)
        results = await mem.search("Python")
        assert len(results) == 1
        assert results[0].name == "py-info"

    async def test_search_with_type_filter(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(return_value=[])
        mem = PostgresqlPersistentMemory(pool)
        results = await mem.search("test", memory_type="tip")
        assert results == []
        # Verify the type-filtered query path was used.
        conn.fetch.assert_awaited_once()

    async def test_update(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value={"id": "r1"})
        conn.execute = AsyncMock()
        mem = PostgresqlPersistentMemory(pool)

        await mem.update("greeting", "Updated!")
        conn.execute.assert_awaited_once()

    async def test_update_with_type_and_metadata(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value={"id": "r1"})
        conn.execute = AsyncMock()
        mem = PostgresqlPersistentMemory(pool)

        await mem.update(
            "greeting",
            "Updated!",
            memory_type="reference",
            metadata={"v": 2},
        )
        conn.execute.assert_awaited_once()

    async def test_update_with_type_only(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value={"id": "r1"})
        conn.execute = AsyncMock()
        mem = PostgresqlPersistentMemory(pool)

        await mem.update("greeting", "Updated!", memory_type="tip")
        conn.execute.assert_awaited_once()

    async def test_update_with_metadata_only(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value={"id": "r1"})
        conn.execute = AsyncMock()
        mem = PostgresqlPersistentMemory(pool)

        await mem.update("greeting", "Updated!", metadata={"v": 3})
        conn.execute.assert_awaited_once()

    async def test_update_missing_raises(self, pool_conn):
        pool, conn = pool_conn
        conn.fetchrow = AsyncMock(return_value=None)
        mem = PostgresqlPersistentMemory(pool)

        with pytest.raises(KeyError):
            await mem.update("nonexistent", "content")

    async def test_forget_found(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 1")
        mem = PostgresqlPersistentMemory(pool)
        assert await mem.forget("greeting") is True

    async def test_forget_missing(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock(return_value="DELETE 0")
        mem = PostgresqlPersistentMemory(pool)
        assert await mem.forget("nonexistent") is False

    async def test_list_memories_all(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "r1",
                    "name": "a",
                    "content": "aa",
                    "memory_type": "fact",
                    "metadata": "{}",
                    "created_at": "",
                    "updated_at": "",
                },
                {
                    "id": "r2",
                    "name": "b",
                    "content": "bb",
                    "memory_type": "tip",
                    "metadata": "{}",
                    "created_at": "",
                    "updated_at": "",
                },
            ]
        )
        mem = PostgresqlPersistentMemory(pool)
        records = await mem.list_memories()
        assert len(records) == 2

    async def test_list_memories_filtered(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "r1",
                    "name": "a",
                    "content": "aa",
                    "memory_type": "fact",
                    "metadata": "{}",
                    "created_at": "",
                    "updated_at": "",
                },
            ]
        )
        mem = PostgresqlPersistentMemory(pool)
        records = await mem.list_memories(memory_type="fact")
        assert len(records) == 1
        assert records[0].memory_type == "fact"


# ── PostgresqlKnowledgeStore ────────────────────────────────────────────


class TestPostgresqlKnowledgeStore:
    """Unit tests for the PostgreSQL RAG knowledge store."""

    async def test_ingest(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        store = PostgresqlKnowledgeStore(pool)

        doc_id = await store.ingest("Some content to store.")
        assert isinstance(doc_id, str)
        assert len(doc_id) > 0
        # At least one chunk should have been inserted.
        assert conn.execute.await_count >= 1

    async def test_ingest_with_metadata(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        store = PostgresqlKnowledgeStore(pool)

        doc_id = await store.ingest("Content here.", metadata={"author": "test"})
        assert isinstance(doc_id, str)

    async def test_query_returns_results(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "k1",
                    "document_id": "d1",
                    "content": "Python is great for data science",
                    "metadata": '{"topic": "python"}',
                },
                {
                    "id": "k2",
                    "document_id": "d2",
                    "content": "JavaScript runs in browsers",
                    "metadata": "{}",
                },
            ]
        )
        store = PostgresqlKnowledgeStore(pool)
        results = await store.query("Python")

        assert len(results) >= 1
        assert isinstance(results[0], RetrievalResult)
        # The Python chunk should rank first due to keyword match.
        assert "Python" in results[0].content

    async def test_query_no_results(self, pool_conn):
        pool, conn = pool_conn
        conn.fetch = AsyncMock(return_value=[])
        store = PostgresqlKnowledgeStore(pool)
        results = await store.query("nonexistent")
        assert results == []

    async def test_query_empty_question(self, pool_conn):
        pool, conn = pool_conn
        store = PostgresqlKnowledgeStore(pool)
        results = await store.query("")
        assert results == []

    def test_chunk_empty(self, pool_conn):
        pool, _ = pool_conn
        store = PostgresqlKnowledgeStore(pool)
        assert store._chunk("") == []

    def test_chunk_short_text(self, pool_conn):
        pool, _ = pool_conn
        store = PostgresqlKnowledgeStore(pool)
        result = store._chunk("Hello world.")
        assert len(result) >= 1
        assert "Hello world." in result[0]

    async def test_ingest_empty(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        store = PostgresqlKnowledgeStore(pool)

        doc_id = await store.ingest("")
        assert isinstance(doc_id, str)
        # No chunks to insert for empty content.
        conn.execute.assert_not_awaited()


# ── PostgresqlSearchBackend.index ───────────────────────────────────────


class TestPostgresqlSearchIndex:
    """Tests for the index method with unique-violation handling."""

    async def test_index_success(self, pool_conn):
        pool, conn = pool_conn
        conn.execute = AsyncMock()
        backend = PostgresqlSearchBackend(pool)

        chunk = Chunk(id="c1", document_id="d1", content="text", chunk_index=0)
        assert await backend.index(chunk, [0.1, 0.2], document_title="T") is True

    async def test_index_duplicate(self, pool_conn):
        pool, conn = pool_conn

        # Simulate asyncpg.UniqueViolationError.  Since asyncpg may or
        # may not be installed, create a matching exception class.
        import asyncpg as _asyncpg

        conn.execute = AsyncMock(side_effect=_asyncpg.UniqueViolationError(""))
        backend = PostgresqlSearchBackend(pool)

        chunk = Chunk(id="c1", document_id="d1", content="text", chunk_index=0)
        assert await backend.index(chunk) is False
