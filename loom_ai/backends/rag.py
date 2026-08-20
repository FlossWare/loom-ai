"""RAG pipeline backends: document ingestion, embeddings, and hybrid search.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
DocumentIngester     -- ingest documents with metadata and provenance tracking
EmbeddingStore       -- store and retrieve embeddings with cosine similarity
HybridSearcher       -- combine keyword and vector search
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass, field

from loom_ai.models_core import RetrievalResult

# Characters-per-token estimate (shared with knowledge.py).
_CHARS_PER_TOKEN = 4

# Sentence-split pattern: split on ". " or newline.
_SPLIT_RE = re.compile(r"(?<=\. )|\n")


# ── Data models ──────────────────────────────────────────────────────────


@dataclass
class DocumentRecord:
    """Internal record tracking an ingested document."""

    id: str
    content: str
    chunk_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    content_hash: str = ""
    created_at: str = ""


@dataclass
class ChunkRecord:
    """Internal record for a single text chunk."""

    id: str
    doc_id: str
    content: str
    index: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class EmbeddingRecord:
    """An embedding vector associated with a chunk."""

    id: str
    chunk_id: str
    vector: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────


def _content_hash(text: str) -> str:
    """Return a SHA-256 hex digest for *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()  # noqa: S324  # NOSONAR — content-addressing hash, not used for security


def _simple_embedding(text: str, dim: int = 64) -> list[float]:
    """Generate a deterministic pseudo-embedding from *text*.

    This is a toy embedding function for environments without a real
    embedding model.  It hashes character bigrams into buckets and
    normalises to a unit vector.
    """
    vec = [0.0] * dim
    lower = text.lower()
    for i in range(len(lower) - 1):
        bigram = lower[i : i + 2]
        bucket = hash(bigram) % dim
        vec[bucket] += 1.0

    # L2-normalise so cosine similarity is a dot product.
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (norm_a * norm_b)


def _keyword_score(text: str, words: list[str]) -> float:
    """Count how many times *words* appear in *text* (case-insensitive)."""
    lower = text.lower()
    return float(sum(lower.count(w) for w in words))


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentence-like segments."""
    parts = _SPLIT_RE.split(text)
    return [p for p in parts if p]


def _chunk_text(
    content: str,
    *,
    max_tokens: int = 512,
    overlap: int = 50,
) -> list[str]:
    """Split *content* into overlapping token-bounded chunks."""
    if not content:
        return []

    sentences = _split_sentences(content)
    if not sentences:
        return []

    max_chars = max_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap * _CHARS_PER_TOKEN

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        slen = len(sentence)
        if current and current_len + slen > max_chars:
            chunks.append("".join(current))
            # Build overlap from tail.
            tail: list[str] = []
            total = 0
            for s in reversed(current):
                if total + len(s) > overlap_chars:
                    break
                tail.append(s)
                total += len(s)
            tail.reverse()
            current = tail
            current_len = total

        current.append(sentence)
        current_len += slen

    if current:
        chunks.append("".join(current))

    return chunks


# ── DocumentIngester ─────────────────────────────────────────────────────


class DocumentIngester:
    """Ingest documents with metadata, chunking, and provenance tracking.

    Each document is chunked, fingerprinted (SHA-256), and stored with
    provenance metadata recording the source and ingestion context.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 512,
        overlap: int = 50,
    ) -> None:
        self._max_tokens = max_tokens
        self._overlap = overlap

        # doc_id -> DocumentRecord
        self._documents: dict[str, DocumentRecord] = {}
        # chunk_id -> ChunkRecord
        self._chunks: dict[str, ChunkRecord] = {}
        # content_hash -> doc_id  (deduplication index)
        self._hash_index: dict[str, str] = {}

    async def ingest(
        self,
        content: str,
        *,
        metadata: dict | None = None,
        provenance: dict | None = None,
    ) -> str:
        """Ingest *content*, chunk it, and return a document id.

        If a document with the same content hash already exists, the
        existing document id is returned and no duplicate is stored.
        """
        chash = _content_hash(content)

        # Deduplicate by content hash.
        if chash in self._hash_index:
            return self._hash_index[chash]

        doc_id = str(uuid.uuid4())
        pieces = _chunk_text(
            content,
            max_tokens=self._max_tokens,
            overlap=self._overlap,
        )

        chunk_ids: list[str] = []
        for idx, piece in enumerate(pieces):
            chunk_id = str(uuid.uuid4())
            self._chunks[chunk_id] = ChunkRecord(
                id=chunk_id,
                doc_id=doc_id,
                content=piece,
                index=idx,
                metadata=dict(metadata) if metadata else {},
            )
            chunk_ids.append(chunk_id)

        self._documents[doc_id] = DocumentRecord(
            id=doc_id,
            content=content,
            chunk_ids=chunk_ids,
            metadata=dict(metadata) if metadata else {},
            provenance=dict(provenance) if provenance else {},
            content_hash=chash,
        )
        self._hash_index[chash] = doc_id
        return doc_id

    async def get_document(self, doc_id: str) -> DocumentRecord | None:
        """Return a document record by id, or ``None``."""
        return self._documents.get(doc_id)

    async def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        """Return a chunk record by id, or ``None``."""
        return self._chunks.get(chunk_id)

    async def get_chunks_for_document(self, doc_id: str) -> list[ChunkRecord]:
        """Return all chunks belonging to *doc_id*."""
        doc = self._documents.get(doc_id)
        if doc is None:
            return []
        return [self._chunks[cid] for cid in doc.chunk_ids if cid in self._chunks]

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its chunks.  Return ``True`` if it existed."""
        doc = self._documents.pop(doc_id, None)
        if doc is None:
            return False
        for cid in doc.chunk_ids:
            self._chunks.pop(cid, None)
        self._hash_index.pop(doc.content_hash, None)
        return True

    @property
    def document_count(self) -> int:
        """Number of stored documents."""
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        """Number of stored chunks."""
        return len(self._chunks)


# ── EmbeddingStore ───────────────────────────────────────────────────────


class EmbeddingStore:
    """Store and retrieve embeddings with cosine similarity search.

    Uses a simple deterministic bigram hash as a fallback when no real
    embedding model is available.
    """

    def __init__(self, *, dim: int = 64) -> None:
        self._dim = dim
        # embedding_id -> EmbeddingRecord
        self._embeddings: dict[str, EmbeddingRecord] = {}
        # chunk_id -> embedding_id
        self._chunk_index: dict[str, str] = {}

    async def store(
        self,
        chunk_id: str,
        text: str,
        *,
        vector: list[float] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Compute (or accept) an embedding for *text* and store it.

        If *vector* is ``None``, a deterministic pseudo-embedding is
        generated.  Returns the embedding id.
        """
        emb_id = str(uuid.uuid4())
        vec = vector if vector is not None else _simple_embedding(text, self._dim)
        self._embeddings[emb_id] = EmbeddingRecord(
            id=emb_id,
            chunk_id=chunk_id,
            vector=vec,
            metadata=dict(metadata) if metadata else {},
        )
        self._chunk_index[chunk_id] = emb_id
        return emb_id

    async def search(
        self,
        query: str,
        *,
        vector: list[float] | None = None,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Return the top *limit* ``(chunk_id, similarity)`` pairs.

        If *vector* is ``None``, the query text is embedded using the
        built-in pseudo-embedding function.
        """
        qvec = vector if vector is not None else _simple_embedding(query, self._dim)

        scored: list[tuple[str, float]] = []
        for rec in self._embeddings.values():
            sim = _cosine_similarity(qvec, rec.vector)
            scored.append((rec.chunk_id, sim))

        scored.sort(key=lambda t: (-t[1], t[0]))
        return scored[:limit]

    async def get_embedding(self, chunk_id: str) -> EmbeddingRecord | None:
        """Return the embedding for *chunk_id*, or ``None``."""
        emb_id = self._chunk_index.get(chunk_id)
        if emb_id is None:
            return None
        return self._embeddings.get(emb_id)

    async def delete(self, chunk_id: str) -> bool:
        """Remove the embedding for *chunk_id*.  Return ``True`` if it existed."""
        emb_id = self._chunk_index.pop(chunk_id, None)
        if emb_id is None:
            return False
        self._embeddings.pop(emb_id, None)
        return True

    @property
    def count(self) -> int:
        """Number of stored embeddings."""
        return len(self._embeddings)


# ── HybridSearcher ───────────────────────────────────────────────────────


class HybridSearcher:
    """Combine keyword and vector search with weighted score fusion.

    Uses Reciprocal Rank Fusion (RRF) by default to merge keyword and
    vector result lists into a single ranked output.
    """

    def __init__(
        self,
        ingester: DocumentIngester,
        embedding_store: EmbeddingStore,
        *,
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
        rrf_k: int = 60,
    ) -> None:
        self._ingester = ingester
        self._embedding_store = embedding_store
        self._keyword_weight = keyword_weight
        self._vector_weight = vector_weight
        self._rrf_k = rrf_k

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        mode: str = "hybrid",
    ) -> list[RetrievalResult]:
        """Search for *query* using the specified *mode*.

        Modes:
        - ``"keyword"``  -- keyword scoring only
        - ``"vector"``   -- cosine similarity only
        - ``"hybrid"``   -- reciprocal rank fusion of both
        """
        if mode == "keyword":
            return await self._keyword_search(query, limit=limit)
        if mode == "vector":
            return await self._vector_search(query, limit=limit)

        # Hybrid: RRF of keyword and vector rankings.
        kw_results = await self._keyword_search(query, limit=limit * 2)
        vec_results = await self._vector_search(query, limit=limit * 2)

        return self._rrf_merge(kw_results, vec_results, limit=limit)

    # -- internal ------------------------------------------------------------

    async def _keyword_search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Score chunks by keyword occurrence."""
        words = query.lower().split()
        if not words:
            return []

        scored: list[tuple[str, float]] = []
        for chunk_id, chunk in self._ingester._chunks.items():
            score = _keyword_score(chunk.content, words)
            if score > 0:
                scored.append((chunk_id, score))

        scored.sort(key=lambda t: (-t[1], t[0]))

        results: list[RetrievalResult] = []
        for chunk_id, score in scored[:limit]:
            chunk = self._ingester._chunks[chunk_id]
            results.append(
                RetrievalResult(
                    content=chunk.content,
                    score=score,
                    source=chunk.doc_id,
                    chunk_id=chunk_id,
                    metadata=dict(chunk.metadata),
                )
            )
        return results

    async def _vector_search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Score chunks by cosine similarity."""
        pairs = await self._embedding_store.search(query, limit=limit)

        results: list[RetrievalResult] = []
        for chunk_id, sim in pairs:
            chunk = self._ingester._chunks.get(chunk_id)
            if chunk is None:
                continue
            results.append(
                RetrievalResult(
                    content=chunk.content,
                    score=sim,
                    source=chunk.doc_id,
                    chunk_id=chunk_id,
                    metadata=dict(chunk.metadata),
                )
            )
        return results

    def _rrf_merge(
        self,
        kw_results: list[RetrievalResult],
        vec_results: list[RetrievalResult],
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Merge two ranked lists using Reciprocal Rank Fusion."""
        k = self._rrf_k
        scores: dict[str, float] = {}
        result_map: dict[str, RetrievalResult] = {}

        for rank, r in enumerate(kw_results):
            rrf = self._keyword_weight / (k + rank + 1)
            scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + rrf
            result_map[r.chunk_id] = r

        for rank, r in enumerate(vec_results):
            rrf = self._vector_weight / (k + rank + 1)
            scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + rrf
            result_map[r.chunk_id] = r

        ranked = sorted(scores.items(), key=lambda t: (-t[1], t[0]))

        merged: list[RetrievalResult] = []
        for chunk_id, score in ranked[:limit]:
            r = result_map[chunk_id]
            merged.append(
                RetrievalResult(
                    content=r.content,
                    score=score,
                    source=r.source,
                    chunk_id=r.chunk_id,
                    metadata=r.metadata,
                )
            )
        return merged
