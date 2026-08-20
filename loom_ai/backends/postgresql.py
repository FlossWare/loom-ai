"""PostgreSQL + pgvector backend implementations for loom-ai.

Optional backend -- requires ``asyncpg`` (and optionally ``pgvector``)
which are installed via::

    pip install flossware-loom-ai[postgresql]

All asyncpg imports are guarded with ``try``/``except`` so the rest of
the package keeps working when the driver is absent.

Classes
-------
PostgresqlStorageBackend       -- document / chunk / embedding persistence
PostgresqlSearchBackend        -- full-text + pgvector semantic search
PostgresqlSecretsBackend       -- encrypted-at-rest secret storage
PostgresqlPersistentMemory     -- named memory store (phase-1 #91)
PostgresqlKnowledgeStore       -- RAG pipeline backed by PostgreSQL
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any

from loom_ai.models import (
    Chunk,
    Document,
    Embedding,
    SearchResult,
)
from loom_ai.models_phase1 import MemoryRecord, RetrievalResult

try:
    import asyncpg  # type: ignore[import-untyped]

    _HAS_ASYNCPG = True
except ImportError:
    asyncpg = None  # type: ignore[assignment]
    _HAS_ASYNCPG = False

try:
    from cryptography.fernet import Fernet, InvalidToken

    _HAS_FERNET = True
except ImportError:
    Fernet = None  # type: ignore[assignment,misc]
    InvalidToken = Exception  # type: ignore[assignment,misc]
    _HAS_FERNET = False


_DELETE_ONE = "DELETE 1"
_shared_pool: Any = None
_shared_pool_lock = asyncio.Lock()


def _require_asyncpg() -> None:
    """Raise a helpful error when asyncpg is not installed."""
    if not _HAS_ASYNCPG:
        raise ImportError(
            "PostgreSQL backends require 'asyncpg'.  "
            "Install with: pip install flossware-loom-ai[postgresql]"
        )


def _dsn_from_env() -> str:
    """Build a DSN from ``LOOM_PG_*`` environment variables."""
    host = os.environ.get("LOOM_PG_HOST", "localhost")
    port = os.environ.get("LOOM_PG_PORT", "5432")
    user = os.environ.get("LOOM_PG_USER", "loom")
    # NOSONAR — credential read from environment, never hardcoded
    credential = os.environ.get("LOOM_PG_PASSWORD", "")
    database = os.environ.get("LOOM_PG_DATABASE", "loom")
    encoded_credential = urllib.parse.quote_plus(credential)
    return f"postgresql://{user}:{encoded_credential}@{host}:{port}/{database}"


async def get_shared_pool() -> Any:
    """Return a module-level shared asyncpg pool, creating it on first call.

    All PostgreSQL backends should share one pool to avoid redundant
    connections.  Call :func:`close_shared_pool` during shutdown.

    Uses an asyncio lock to prevent concurrent coroutines from creating
    duplicate pools.
    """
    global _shared_pool
    async with _shared_pool_lock:
        if _shared_pool is None:
            _require_asyncpg()
            _shared_pool = await asyncpg.create_pool(dsn=_dsn_from_env())
    return _shared_pool


async def close_shared_pool() -> None:
    """Close the shared pool if it was created.  Safe to call multiple times."""
    global _shared_pool
    async with _shared_pool_lock:
        if _shared_pool is not None:
            await _shared_pool.close()
            _shared_pool = None


# ======================================================================
# StorageBackend
# ======================================================================


class PostgresqlStorageBackend:
    """PostgreSQL-backed document / chunk / embedding storage.

    Satisfies :class:`~loom_ai.protocols.StorageBackend` via structural
    subtyping.

    Parameters
    ----------
    pool:
        An ``asyncpg.Pool`` instance.  Use :meth:`from_env` to build one
        from environment variables.
    """

    def __init__(self, pool: Any) -> None:
        _require_asyncpg()
        self._pool = pool

    @classmethod
    async def from_env(cls, *, pool: Any = None) -> PostgresqlStorageBackend:
        """Create an instance using ``LOOM_PG_*`` env vars."""
        _require_asyncpg()
        p = pool if pool is not None else await get_shared_pool()
        return cls(p)

    # -- Documents --------------------------------------------------------

    async def store_document(self, document: Document) -> str:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (id, title, content, url, category,
                                       metadata, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    url = EXCLUDED.url,
                    category = EXCLUDED.category,
                    metadata = EXCLUDED.metadata
                """,
                document.id,
                document.title,
                document.content,
                document.url,
                document.category,
                json.dumps(document.metadata),
                document.created_at or datetime.now(timezone.utc).isoformat(),
            )
        return document.id

    async def get_document(self, document_id: str) -> Document | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE id = $1", document_id
            )
        if row is None:
            return None
        return Document(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            url=row["url"],
            category=row["category"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )

    async def list_documents(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM documents ORDER BY created_at LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [
            Document(
                id=r["id"],
                title=r["title"],
                content=r["content"],
                url=r["url"],
                category=r["category"],
                metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def delete_document(self, document_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE id = $1", document_id
            )
        return result == _DELETE_ONE

    async def count_documents(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM documents")

    # -- Chunks -----------------------------------------------------------

    async def store_chunks(self, document_id: str, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO chunks (id, document_id, content, chunk_index,
                                    content_hash)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    chunk_index = EXCLUDED.chunk_index,
                    content_hash = EXCLUDED.content_hash
                """,
                [
                    (c.id, document_id, c.content, c.chunk_index, c.content_hash)
                    for c in chunks
                ],
            )
        return len(chunks)

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM chunks WHERE document_id = $1 ORDER BY chunk_index",
                document_id,
            )
        return [
            Chunk(
                id=r["id"],
                document_id=r["document_id"],
                content=r["content"],
                chunk_index=r["chunk_index"],
                content_hash=r.get("content_hash", ""),
            )
            for r in rows
        ]

    async def get_chunks_batch(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM chunks WHERE id = ANY($1::text[])", chunk_ids
            )
        return [
            Chunk(
                id=r["id"],
                document_id=r["document_id"],
                content=r["content"],
                chunk_index=r["chunk_index"],
                content_hash=r.get("content_hash", ""),
            )
            for r in rows
        ]

    async def get_pending_chunks(
        self, limit: int, *, after_id: str | None = None
    ) -> list[Chunk]:
        async with self._pool.acquire() as conn:
            if after_id:
                rows = await conn.fetch(
                    """
                    SELECT c.* FROM chunks c
                    LEFT JOIN embeddings e ON c.id = e.chunk_id
                    WHERE e.id IS NULL AND c.id > $1
                    ORDER BY c.id LIMIT $2
                    """,
                    after_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT c.* FROM chunks c
                    LEFT JOIN embeddings e ON c.id = e.chunk_id
                    WHERE e.id IS NULL
                    ORDER BY c.id LIMIT $1
                    """,
                    limit,
                )
        return [
            Chunk(
                id=r["id"],
                document_id=r["document_id"],
                content=r["content"],
                chunk_index=r["chunk_index"],
                content_hash=r.get("content_hash", ""),
            )
            for r in rows
        ]

    async def delete_chunks(self, document_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM chunks WHERE document_id = $1", document_id
            )
        return not result.endswith(" 0")

    async def count_chunks(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM chunks")

    # -- Embeddings -------------------------------------------------------

    async def store_embeddings(self, embeddings: list[Embedding]) -> int:
        if not embeddings:
            return 0
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO embeddings (id, chunk_id, vector, model,
                                        provider, dimensions)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO UPDATE SET
                    vector = EXCLUDED.vector,
                    model = EXCLUDED.model
                """,
                [
                    (
                        e.id,
                        e.chunk_id,
                        json.dumps(e.vector),
                        e.model,
                        e.provider,
                        e.dimensions,
                    )
                    for e in embeddings
                ],
            )
        return len(embeddings)

    async def count_embeddings(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM embeddings")


# ======================================================================
# SearchBackend
# ======================================================================


class PostgresqlSearchBackend:
    """PostgreSQL full-text + pgvector semantic search backend.

    Satisfies :class:`~loom_ai.protocols.SearchBackend` via structural
    subtyping.
    """

    def __init__(self, pool: Any) -> None:
        _require_asyncpg()
        self._pool = pool

    @classmethod
    async def from_env(cls, *, pool: Any = None) -> PostgresqlSearchBackend:
        """Create an instance using ``LOOM_PG_*`` env vars."""
        _require_asyncpg()
        p = pool if pool is not None else await get_shared_pool()
        return cls(p)

    async def index(
        self,
        chunk: Chunk,
        vector: list[float] | None = None,
        *,
        document_title: str | None = None,
        source: str | None = None,
    ) -> bool:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO search_index
                    (chunk_id, content, vector, document_title, source)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    vector = EXCLUDED.vector,
                    document_title = EXCLUDED.document_title,
                    source = EXCLUDED.source
                """,
                chunk.id,
                chunk.content,
                json.dumps(vector) if vector else None,
                document_title or "",
                source or "",
            )
            return True

    async def text_search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, content, document_title, source,
                       ts_rank(to_tsvector('english', content),
                               plainto_tsquery('english', $1)) AS score
                FROM search_index
                WHERE to_tsvector('english', content)
                      @@ plainto_tsquery('english', $1)
                ORDER BY score DESC
                LIMIT $2
                """,
                query,
                limit,
            )
        return [
            SearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                score=float(r["score"]),
                document_title=r["document_title"],
                source=r["source"],
            )
            for r in rows
        ]

    async def semantic_search(
        self, vector: list[float], *, limit: int = 10
    ) -> list[SearchResult]:
        vec_str = json.dumps(vector)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, content, document_title, source,
                       1 - (vector::vector <=> $1::vector) AS score
                FROM search_index
                WHERE vector IS NOT NULL
                ORDER BY vector::vector <=> $1::vector
                LIMIT $2
                """,
                vec_str,
                limit,
            )
        return [
            SearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                score=float(r["score"]),
                document_title=r["document_title"],
                source=r["source"],
            )
            for r in rows
        ]

    async def hybrid_search(
        self,
        query: str,
        vector: list[float],
        *,
        limit: int = 10,
        text_weight: float = 0.5,
    ) -> list[SearchResult]:
        text_results = await self.text_search(query, limit=limit * 3)
        sem_results = await self.semantic_search(vector, limit=limit * 3)

        sem_weight = 1.0 - text_weight
        k = 60  # RRF constant

        rrf: dict[str, float] = {}
        meta: dict[str, SearchResult] = {}

        for rank, sr in enumerate(text_results, start=1):
            rrf[sr.chunk_id] = rrf.get(sr.chunk_id, 0.0) + text_weight * (
                1.0 / (k + rank)
            )
            meta[sr.chunk_id] = sr

        for rank, sr in enumerate(sem_results, start=1):
            rrf[sr.chunk_id] = rrf.get(sr.chunk_id, 0.0) + sem_weight * (
                1.0 / (k + rank)
            )
            if sr.chunk_id not in meta:
                meta[sr.chunk_id] = sr

        ranked = sorted(rrf.items(), key=lambda t: t[1], reverse=True)

        results: list[SearchResult] = []
        for chunk_id, score in ranked[:limit]:
            base = meta[chunk_id]
            results.append(
                SearchResult(
                    chunk_id=base.chunk_id,
                    content=base.content,
                    score=score,
                    document_title=base.document_title,
                    source=base.source,
                )
            )
        return results

    async def delete_by_document(self, document_id: str) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM search_index
                WHERE chunk_id IN (
                    SELECT id FROM chunks WHERE document_id = $1
                )
                """,
                document_id,
            )
        # result is e.g. "DELETE 5"
        try:
            return int(result.split()[-1])
        except (IndexError, ValueError):
            return 0


# ======================================================================
# SecretsBackend
# ======================================================================


class PostgresqlSecretsBackend:
    """PostgreSQL-backed secret storage with optional Fernet encryption.

    Satisfies :class:`~loom_ai.protocols.SecretsBackend` via structural
    subtyping.

    When ``LOOM_SECRETS_KEY`` is set (a valid Fernet key), values are
    encrypted before storage and decrypted on retrieval.  When unset,
    values are stored as plaintext for backward compatibility.
    """

    def __init__(self, pool: Any, *, encryption_key: str | None = None) -> None:
        _require_asyncpg()
        self._pool = pool
        self._fernet: Any = None
        if encryption_key:
            if not _HAS_FERNET:
                raise ImportError(
                    "Encrypted secrets require 'cryptography'.  "
                    "Install with: pip install cryptography"
                )
            key_bytes = (
                encryption_key.encode()
                if isinstance(encryption_key, str)
                else encryption_key
            )
            self._fernet = Fernet(key_bytes)

    @classmethod
    async def from_env(cls, *, pool: Any = None) -> PostgresqlSecretsBackend:
        """Create an instance using ``LOOM_PG_*`` env vars."""
        _require_asyncpg()
        p = pool if pool is not None else await get_shared_pool()
        key = os.environ.get("LOOM_SECRETS_KEY")
        return cls(p, encryption_key=key)

    def _encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            return plaintext
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        if self._fernet is None:
            return ciphertext
        return self._fernet.decrypt(ciphertext.encode()).decode()

    async def get(self, name: str) -> str | None:
        async with self._pool.acquire() as conn:
            raw = await conn.fetchval("SELECT value FROM secrets WHERE name = $1", name)
        if raw is None:
            return None
        return self._decrypt(raw)

    async def set(self, name: str, value: str) -> bool:
        encrypted = self._encrypt(value)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO secrets (name, value)
                VALUES ($1, $2)
                ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value
                """,
                name,
                encrypted,
            )
        return True

    async def list_names(self) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT name FROM secrets ORDER BY name")
        return [r["name"] for r in rows]

    async def delete(self, name: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM secrets WHERE name = $1", name)
        return result == _DELETE_ONE


# ======================================================================
# PersistentMemoryBackend (#91)
# ======================================================================


class PostgresqlPersistentMemory:
    """PostgreSQL-backed persistent memory store.

    Satisfies :class:`~loom_ai.contracts_phase1.PersistentMemoryBackend`
    via structural subtyping.

    Stores named memory records with type, metadata, and timestamps in a
    ``memories`` table.
    """

    def __init__(self, pool: Any) -> None:
        _require_asyncpg()
        self._pool = pool

    @classmethod
    async def from_env(cls, *, pool: Any = None) -> PostgresqlPersistentMemory:
        """Create an instance using ``LOOM_PG_*`` env vars."""
        _require_asyncpg()
        p = pool if pool is not None else await get_shared_pool()
        return cls(p)

    async def store(
        self,
        name: str,
        content: str,
        *,
        memory_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Store content under *name* and return the record id."""
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memories (id, name, content, memory_type,
                                      metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (name) DO UPDATE SET
                    id = EXCLUDED.id,
                    content = EXCLUDED.content,
                    memory_type = EXCLUDED.memory_type,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                record_id,
                name,
                content,
                memory_type,
                json.dumps(metadata or {}),
                now,
                now,
            )
        return record_id

    async def recall(self, name: str) -> MemoryRecord | None:
        """Recall a memory by name, or ``None`` if not found."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM memories WHERE name = $1", name)
        if row is None:
            return None
        return MemoryRecord(
            id=row["id"],
            name=row["name"],
            content=row["content"],
            memory_type=row["memory_type"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[MemoryRecord]:
        """Search memories using case-insensitive substring matching."""
        async with self._pool.acquire() as conn:
            if memory_type is not None:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories
                    WHERE memory_type = $1
                      AND (name ILIKE '%' || $2 || '%'
                           OR content ILIKE '%' || $2 || '%')
                    LIMIT $3
                    """,
                    memory_type,
                    query,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories
                    WHERE name ILIKE '%' || $1 || '%'
                       OR content ILIKE '%' || $1 || '%'
                    LIMIT $2
                    """,
                    query,
                    limit,
                )
        return [
            MemoryRecord(
                id=r["id"],
                name=r["name"],
                content=r["content"],
                memory_type=r["memory_type"],
                metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def update(
        self,
        name: str,
        content: str,
        *,
        memory_type: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Overwrite the content of an existing memory."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM memories WHERE name = $1", name)
            if row is None:
                msg = f"No memory with name '{name}'"
                raise KeyError(msg)

            if memory_type is not None and metadata is not None:
                await conn.execute(
                    """
                    UPDATE memories
                    SET content = $1, memory_type = $2, metadata = $3,
                        updated_at = $4
                    WHERE name = $5
                    """,
                    content,
                    memory_type,
                    json.dumps(metadata),
                    now,
                    name,
                )
            elif memory_type is not None:
                await conn.execute(
                    """
                    UPDATE memories
                    SET content = $1, memory_type = $2, updated_at = $3
                    WHERE name = $4
                    """,
                    content,
                    memory_type,
                    now,
                    name,
                )
            elif metadata is not None:
                await conn.execute(
                    """
                    UPDATE memories
                    SET content = $1, metadata = $2, updated_at = $3
                    WHERE name = $4
                    """,
                    content,
                    json.dumps(metadata),
                    now,
                    name,
                )
            else:
                await conn.execute(
                    """
                    UPDATE memories
                    SET content = $1, updated_at = $2
                    WHERE name = $3
                    """,
                    content,
                    now,
                    name,
                )

    async def forget(self, name: str) -> bool:
        """Remove a memory by name.  Return ``True`` if it existed."""
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM memories WHERE name = $1", name)
        return result == _DELETE_ONE

    async def list_memories(
        self, *, memory_type: str | None = None
    ) -> list[MemoryRecord]:
        """Return stored memories, optionally filtered by type."""
        async with self._pool.acquire() as conn:
            if memory_type is not None:
                rows = await conn.fetch(
                    "SELECT * FROM memories WHERE memory_type = $1 ORDER BY name",
                    memory_type,
                )
            else:
                rows = await conn.fetch("SELECT * FROM memories ORDER BY name")
        return [
            MemoryRecord(
                id=r["id"],
                name=r["name"],
                content=r["content"],
                memory_type=r["memory_type"],
                metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]


# ======================================================================
# KnowledgeStore (RAG pipeline)
# ======================================================================


class PostgresqlKnowledgeStore:
    """PostgreSQL-backed RAG knowledge store.

    Satisfies :class:`~loom_ai.contracts_phase1.KnowledgePipeline` via
    structural subtyping.  Ingests content into chunks stored in a
    ``knowledge_chunks`` table and retrieves by keyword scoring.

    Parameters
    ----------
    pool:
        An ``asyncpg.Pool`` instance.
    max_tokens:
        Default token budget for chunking.
    overlap:
        Default overlap (in tokens) for chunking.
    """

    _CHARS_PER_TOKEN = 4

    def __init__(
        self,
        pool: Any,
        *,
        max_tokens: int = 512,
        overlap: int = 50,
    ) -> None:
        _require_asyncpg()
        self._pool = pool
        self._max_tokens = max_tokens
        self._overlap = overlap

    @classmethod
    async def from_env(
        cls,
        *,
        pool: Any = None,
        max_tokens: int = 512,
        overlap: int = 50,
    ) -> PostgresqlKnowledgeStore:
        """Create an instance using ``LOOM_PG_*`` env vars."""
        _require_asyncpg()
        p = pool if pool is not None else await get_shared_pool()
        return cls(p, max_tokens=max_tokens, overlap=overlap)

    async def ingest(
        self,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> str:
        """Chunk *content* and store in PostgreSQL.  Return a document id."""
        doc_id = str(uuid.uuid4())
        pieces = self._chunk(content)

        async with self._pool.acquire() as conn:
            for piece in pieces:
                chunk_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO knowledge_chunks
                        (id, document_id, content, metadata)
                    VALUES ($1, $2, $3, $4)
                    """,
                    chunk_id,
                    doc_id,
                    piece,
                    json.dumps(metadata or {}),
                )
        return doc_id

    async def query(
        self,
        question: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Score chunks by keyword occurrence and return top *limit*."""
        words = question.lower().split()
        if not words:
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, document_id, content, metadata FROM knowledge_chunks"
            )

        scored: list[tuple[Any, float]] = []
        for row in rows:
            text_lower = row["content"].lower()
            score = float(sum(text_lower.count(w) for w in words))
            if score > 0:
                scored.append((row, score))

        scored.sort(key=lambda t: (-t[1], t[0]["id"]))

        results: list[RetrievalResult] = []
        for row, score in scored[:limit]:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            results.append(
                RetrievalResult(
                    content=row["content"],
                    score=score,
                    source=row["document_id"],
                    chunk_id=row["id"],
                    metadata=meta,
                )
            )
        return results

    def _chunk(self, content: str) -> list[str]:
        """Split *content* into overlapping token-bounded chunks."""
        if not content:
            return []

        max_chars = self._max_tokens * self._CHARS_PER_TOKEN
        overlap_chars = self._overlap * self._CHARS_PER_TOKEN

        # Split on sentence boundaries and newlines.
        parts = content.replace("\n", "\n ").split(". ")
        sentences = [s for s in parts if s]
        if not sentences:
            return [content]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for sentence in sentences:
            slen = len(sentence)
            if current and current_len + slen > max_chars:
                chunks.append(". ".join(current))
                # Build overlap from trailing sentences.
                tail: list[str] = []
                tail_len = 0
                for s in reversed(current):
                    if tail_len + len(s) > overlap_chars:
                        break
                    tail.append(s)
                    tail_len += len(s)
                tail.reverse()
                current = tail
                current_len = tail_len

            current.append(sentence)
            current_len += slen

        if current:
            chunks.append(". ".join(current))

        return chunks
