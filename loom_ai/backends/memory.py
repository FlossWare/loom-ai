"""In-memory and no-op backend implementations for loom-ai.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
MemoryStorageBackend          -- dict-backed document / chunk / embedding store
MemoryQueueBackend            -- deque-backed named task queues (thread-safe)
NoopEmbeddingBackend          -- zero-vector embedding generator
MemorySearchBackend           -- substring text search + brute-force cosine similarity
MemoryGraphBackend            -- dict-backed knowledge graph with BFS traversal
DisabledGraphBackend          -- raises NotImplementedError for every operation
InMemoryPersistentMemory      -- dict-backed persistent memory store (#91)
"""

from __future__ import annotations

import asyncio
import math
import threading
import uuid
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone

from loom_ai.models import (
    Chunk,
    Document,
    Embedding,
    GraphEdge,
    GraphNode,
    QueueItem,
    SearchResult,
)
from loom_ai.models_phase1 import MemoryRecord

# ── helpers ──────────────────────────────────────────────────────────────


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Returns 0.0 when vectors differ in length or either has zero magnitude.
    """
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    mag_a_sq = 0.0
    mag_b_sq = 0.0
    for x, y in zip(a, b):
        dot += x * y
        mag_a_sq += x * x
        mag_b_sq += y * y
    if mag_a_sq == 0.0 or mag_b_sq == 0.0:
        return 0.0
    return dot / (math.sqrt(mag_a_sq) * math.sqrt(mag_b_sq))


# ══════════════════════════════════════════════════════════════════════════
# StorageBackend
# ══════════════════════════════════════════════════════════════════════════


class MemoryStorageBackend:
    """Fully async, dict-backed storage backend.

    Satisfies :class:`~loom_ai.protocols.StorageBackend` via structural
    subtyping.  Thread-safety is *not* provided -- callers that share an
    instance across threads must add their own synchronisation.
    """

    def __init__(self) -> None:
        # Primary stores (keyed by entity id)
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, Chunk] = {}
        self._embeddings: dict[str, Embedding] = {}

        # Secondary indexes
        self._chunks_by_doc: dict[str, list[str]] = {}
        self._chunk_order: list[str] = []  # insertion order for pagination
        self._embedded_chunk_ids: set[str] = set()

    # -- Documents --------------------------------------------------------

    async def store_document(self, document: Document) -> str:
        self._documents[document.id] = document
        return document.id

    async def get_document(self, document_id: str) -> Document | None:
        return self._documents.get(document_id)

    async def list_documents(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        docs = list(self._documents.values())
        return docs[offset : offset + limit]

    async def delete_document(self, document_id: str) -> bool:
        if document_id not in self._documents:
            return False

        del self._documents[document_id]

        # Cascade: remove chunks and their embeddings
        chunk_ids = self._chunks_by_doc.pop(document_id, [])
        chunk_ids_set = set(chunk_ids)

        for chunk_id in chunk_ids:
            self._chunks.pop(chunk_id, None)
            self._embedded_chunk_ids.discard(chunk_id)

            # Remove every embedding that references this chunk
            stale = [
                eid for eid, emb in self._embeddings.items() if emb.chunk_id == chunk_id
            ]
            for eid in stale:
                del self._embeddings[eid]

        # Rebuild insertion-order list without deleted chunk ids
        self._chunk_order = [
            cid for cid in self._chunk_order if cid not in chunk_ids_set
        ]
        return True

    async def count_documents(self) -> int:
        # async required by StorageBackend protocol contract
        await asyncio.sleep(0)
        return len(self._documents)

    # -- Chunks -----------------------------------------------------------

    async def store_chunks(self, document_id: str, chunks: list[Chunk]) -> int:
        stored = 0
        for chunk in chunks:
            if chunk.id not in self._chunks:
                self._chunks_by_doc.setdefault(document_id, []).append(chunk.id)
                self._chunk_order.append(chunk.id)
            self._chunks[chunk.id] = chunk
            stored += 1
        return stored

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        chunk_ids = self._chunks_by_doc.get(document_id, [])
        chunks = [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]
        chunks.sort(key=lambda c: c.chunk_index)
        return chunks

    async def get_chunks_batch(self, chunk_ids: list[str]) -> list[Chunk]:
        return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]

    async def get_pending_chunks(
        self, limit: int, *, after_id: str | None = None
    ) -> list[Chunk]:
        result: list[Chunk] = []
        past_cursor = after_id is None

        for chunk_id in self._chunk_order:
            if not past_cursor:
                if chunk_id == after_id:
                    past_cursor = True
                continue

            if chunk_id not in self._embedded_chunk_ids and chunk_id in self._chunks:
                result.append(self._chunks[chunk_id])
                if len(result) >= limit:
                    break

        return result

    async def delete_chunks(self, document_id: str) -> bool:
        chunk_ids = self._chunks_by_doc.pop(document_id, [])
        if not chunk_ids:
            return False

        chunk_ids_set = set(chunk_ids)
        for chunk_id in chunk_ids:
            self._chunks.pop(chunk_id, None)
            self._embedded_chunk_ids.discard(chunk_id)

            stale = [
                eid for eid, emb in self._embeddings.items() if emb.chunk_id == chunk_id
            ]
            for eid in stale:
                del self._embeddings[eid]

        self._chunk_order = [
            cid for cid in self._chunk_order if cid not in chunk_ids_set
        ]
        return True

    async def count_chunks(self) -> int:
        return len(self._chunks)

    # -- Embeddings -------------------------------------------------------

    async def store_embeddings(self, embeddings: list[Embedding]) -> int:
        stored = 0
        for emb in embeddings:
            self._embeddings[emb.id] = emb
            self._embedded_chunk_ids.add(emb.chunk_id)
            stored += 1
        return stored

    async def count_embeddings(self) -> int:
        return len(self._embeddings)


# ══════════════════════════════════════════════════════════════════════════
# QueueBackend
# ══════════════════════════════════════════════════════════════════════════


class MemoryQueueBackend:
    """In-memory named task queue using ``collections.deque``.

    Thread-safe via a single lock.  Suitable for single-process
    deployments and testing.

    Satisfies :class:`~loom_ai.protocols.QueueBackend` via structural
    subtyping.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # queue_name -> deque of QueueItem (waiting to be fetched)
        self._queues: dict[str, deque[QueueItem]] = {}
        # queue_name -> {item_id: QueueItem} (currently being processed)
        self._processing: dict[str, dict[str, QueueItem]] = {}

    def _ensure_queue(self, queue_name: str) -> None:
        """Create queue structures if they don't exist yet."""
        if queue_name not in self._queues:
            self._queues[queue_name] = deque()
            self._processing[queue_name] = {}

    async def enqueue(self, queue_name: str, items: list[QueueItem]) -> int:
        with self._lock:
            self._ensure_queue(queue_name)
            count = 0
            for item in items:
                self._queues[queue_name].append(item)
                count += 1
            return count

    async def fetch(
        self, queue_name: str, count: int, worker_id: str
    ) -> list[QueueItem]:
        with self._lock:
            self._ensure_queue(queue_name)
            fetched: list[QueueItem] = []
            for _ in range(min(count, len(self._queues[queue_name]))):
                item = self._queues[queue_name].popleft()
                claimed = replace(item, worker_id=worker_id)
                self._processing[queue_name][claimed.id] = claimed
                fetched.append(claimed)
            return fetched

    async def complete(self, queue_name: str, item_id: str) -> bool:
        with self._lock:
            self._ensure_queue(queue_name)
            if item_id in self._processing[queue_name]:
                del self._processing[queue_name][item_id]
                return True
            return False

    async def requeue(self, queue_name: str, items: list[QueueItem]) -> int:
        with self._lock:
            self._ensure_queue(queue_name)
            count = 0
            for item in items:
                self._processing[queue_name].pop(item.id, None)
                cleared = replace(item, worker_id=None)
                self._queues[queue_name].append(cleared)
                count += 1
            return count

    async def status(self, queue_name: str) -> dict:
        with self._lock:
            self._ensure_queue(queue_name)
            return {
                "queued": len(self._queues[queue_name]),
                "processing": len(self._processing[queue_name]),
            }

    async def list_queues(self) -> list[str]:
        with self._lock:
            return sorted(self._queues.keys())


# ══════════════════════════════════════════════════════════════════════════
# EmbeddingBackend (no-op)
# ══════════════════════════════════════════════════════════════════════════


class NoopEmbeddingBackend:
    """Return zero-vectors of a configurable dimensionality.

    Useful for the *crush* deployment, unit tests, and schema/migration
    verification that does not require semantic similarity.

    Satisfies :class:`~loom_ai.protocols.EmbeddingBackend` via structural
    subtyping.
    """

    def __init__(
        self, default_dimensions: int = 384, default_model: str = "noop"
    ) -> None:
        self._default_dimensions = default_dimensions
        self._default_model = default_model
        self._models: dict[str, int] = {default_model: default_dimensions}

    def register_model(self, name: str, dimensions: int) -> None:
        """Register an additional pseudo-model with specific dimensions.

        Lets tests simulate a multi-model environment without any real
        provider.  Not part of the EmbeddingBackend protocol.
        """
        self._models[name] = dimensions

    def _resolve_dims(self, model: str | None) -> int:
        model = model or self._default_model
        return self._models.get(model, self._default_dimensions)

    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float]]:
        dims = self._resolve_dims(model)
        return [[0.0] * dims for _ in texts]

    async def embed_single(self, text: str, *, model: str | None = None) -> list[float]:
        # text required by EmbeddingBackend protocol contract
        _ = text
        # async required by EmbeddingBackend protocol contract
        await asyncio.sleep(0)
        return [0.0] * self._resolve_dims(model)

    async def available_models(self) -> list[str]:
        return sorted(self._models.keys())

    async def dimensions(self, *, model: str | None = None) -> int:
        return self._resolve_dims(model)


# ══════════════════════════════════════════════════════════════════════════
# SearchBackend
# ══════════════════════════════════════════════════════════════════════════


class MemorySearchBackend:
    """In-memory search backend for the *crush* deployment.

    - ``text_search``: case-insensitive substring matching scored by
      occurrence frequency.
    - ``semantic_search``: brute-force cosine similarity against stored
      vectors.
    - ``hybrid_search``: Reciprocal Rank Fusion (RRF) weighted merge of
      text and semantic results.

    Satisfies :class:`~loom_ai.protocols.SearchBackend` via structural
    subtyping.
    """

    def __init__(self) -> None:
        # chunk_id -> Chunk
        self._chunks: dict[str, Chunk] = {}
        # chunk_id -> document_title
        self._titles: dict[str, str] = {}
        # chunk_id -> source URL / path
        self._sources: dict[str, str] = {}
        # chunk_id -> embedding vector
        self._vectors: dict[str, list[float]] = {}

    async def index(
        self,
        chunk: Chunk,
        vector: list[float] | None = None,
        *,
        document_title: str = "",
        source: str = "",
    ) -> bool:
        # async required by SearchBackend protocol contract
        await asyncio.sleep(0)
        if chunk.id in self._chunks:
            return False
        self._chunks[chunk.id] = chunk
        if document_title:
            self._titles[chunk.id] = document_title
        if source:
            self._sources[chunk.id] = source
        if vector is not None:
            self._vectors[chunk.id] = vector
        return True

    async def text_search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        query_lower = query.lower()
        scored: list[tuple[str, int]] = []
        for chunk_id, chunk in self._chunks.items():
            count = chunk.content.lower().count(query_lower)
            if count > 0:
                scored.append((chunk_id, count))

        if not scored:
            return []

        max_count = max(c for _, c in scored)
        scored.sort(key=lambda t: t[1], reverse=True)

        results: list[SearchResult] = []
        for chunk_id, count in scored[:limit]:
            chunk = self._chunks[chunk_id]
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    content=chunk.content,
                    score=count / max_count if max_count > 0 else 0.0,
                    document_title=self._titles.get(chunk_id, ""),
                    source=self._sources.get(chunk_id, ""),
                )
            )
        return results

    async def semantic_search(
        self, vector: list[float], *, limit: int = 10
    ) -> list[SearchResult]:
        scored: list[tuple[str, float]] = []
        for chunk_id, stored_vec in self._vectors.items():
            sim = _cosine_similarity(vector, stored_vec)
            scored.append((chunk_id, sim))

        scored.sort(key=lambda t: t[1], reverse=True)

        results: list[SearchResult] = []
        for chunk_id, sim in scored[:limit]:
            chunk = self._chunks[chunk_id]
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    content=chunk.content,
                    score=sim,
                    document_title=self._titles.get(chunk_id, ""),
                    source=self._sources.get(chunk_id, ""),
                )
            )
        return results

    async def hybrid_search(
        self,
        query: str,
        vector: list[float],
        *,
        limit: int = 10,
        text_weight: float = 0.5,
    ) -> list[SearchResult]:
        fetch_limit = limit * 3
        text_results = await self.text_search(query, limit=fetch_limit)
        sem_results = await self.semantic_search(vector, limit=fetch_limit)

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
        to_remove = [
            cid
            for cid, chunk in self._chunks.items()
            if chunk.document_id == document_id
        ]
        for cid in to_remove:
            del self._chunks[cid]
            self._titles.pop(cid, None)
            self._sources.pop(cid, None)
            self._vectors.pop(cid, None)
        return len(to_remove)


# ══════════════════════════════════════════════════════════════════════════
# GraphBackend
# ══════════════════════════════════════════════════════════════════════════


class DisabledGraphBackend:
    """Raises ``NotImplementedError`` for every operation.

    Used by the *crush* deployment where no graph database is available.
    The error messages are intentionally descriptive.

    Satisfies :class:`~loom_ai.protocols.GraphBackend` via structural
    subtyping (callers should guard with ``if config.graph is not None``).
    """

    _MSG = (
        "GraphBackend is disabled in this deployment.  "
        "To enable knowledge-graph features, configure a graph backend "
        "(e.g. OrientDB for the 'claude' deployment, or 'memory' for "
        "testing) and set LOOM_GRAPH accordingly."
    )

    async def add_node(self, node: GraphNode) -> str:
        raise NotImplementedError(self._MSG)

    async def get_node(self, node_id: str) -> GraphNode | None:
        raise NotImplementedError(self._MSG)

    async def add_edge(self, edge: GraphEdge) -> str:
        raise NotImplementedError(self._MSG)

    async def get_neighbors(
        self, node_id: str, *, edge_label: str | None = None
    ) -> list[GraphNode]:
        raise NotImplementedError(self._MSG)

    async def traverse(
        self,
        start_id: str,
        *,
        edge_label: str | None = None,
        depth: int = 1,
    ) -> list[GraphNode]:
        raise NotImplementedError(self._MSG)

    async def delete_node(self, node_id: str) -> bool:
        raise NotImplementedError(self._MSG)

    async def delete_edge(self, edge_id: str) -> bool:
        raise NotImplementedError(self._MSG)


class MemoryGraphBackend:
    """In-memory knowledge graph with adjacency-list index and BFS traversal.

    Satisfies :class:`~loom_ai.protocols.GraphBackend` via structural
    subtyping.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        # node_id -> set of edge_ids (both directions)
        self._adjacency: dict[str, set[str]] = {}

    async def add_node(self, node: GraphNode) -> str:
        self._nodes[node.id] = node
        if node.id not in self._adjacency:
            self._adjacency[node.id] = set()
        return node.id

    async def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    async def add_edge(self, edge: GraphEdge) -> str:
        if edge.source not in self._nodes:
            raise ValueError(
                f"Source node '{edge.source}' does not exist.  "
                f"Add it with add_node() first."
            )
        if edge.target not in self._nodes:
            raise ValueError(
                f"Target node '{edge.target}' does not exist.  "
                f"Add it with add_node() first."
            )
        self._edges[edge.id] = edge
        self._adjacency.setdefault(edge.source, set()).add(edge.id)
        self._adjacency.setdefault(edge.target, set()).add(edge.id)
        return edge.id

    async def get_neighbors(
        self, node_id: str, *, edge_label: str | None = None
    ) -> list[GraphNode]:
        edge_ids = self._adjacency.get(node_id, set())
        neighbors: list[GraphNode] = []
        seen: set[str] = set()
        for eid in edge_ids:
            edge = self._edges.get(eid)
            if edge is None:
                continue
            if edge_label is not None and edge.label != edge_label:
                continue
            other_id = edge.target if edge.source == node_id else edge.source
            if other_id not in seen:
                seen.add(other_id)
                node = self._nodes.get(other_id)
                if node is not None:
                    neighbors.append(node)
        return neighbors

    async def traverse(
        self,
        start_id: str,
        *,
        edge_label: str | None = None,
        depth: int = 1,
    ) -> list[GraphNode]:
        """BFS traversal from *start_id* up to *depth* hops."""
        visited: set[str] = {start_id}
        result: list[GraphNode] = []
        frontier: set[str] = {start_id}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                neighbors = await self.get_neighbors(nid, edge_label=edge_label)
                for neighbor in neighbors:
                    if neighbor.id not in visited:
                        visited.add(neighbor.id)
                        next_frontier.add(neighbor.id)
                        result.append(neighbor)
            frontier = next_frontier
            if not frontier:
                break

        return result

    async def delete_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        # Remove all incident edges first
        edge_ids = list(self._adjacency.get(node_id, set()))
        for eid in edge_ids:
            await self.delete_edge(eid)
        del self._nodes[node_id]
        self._adjacency.pop(node_id, None)
        return True

    async def delete_edge(self, edge_id: str) -> bool:
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            return False
        self._adjacency.get(edge.source, set()).discard(edge_id)
        self._adjacency.get(edge.target, set()).discard(edge_id)
        return True


# ══════════════════════════════════════════════════════════════════════════
# PersistentMemoryBackend (#91)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryPersistentMemory:
    """Dict-backed persistent memory store.

    Satisfies :class:`~loom_ai.contracts_phase1.PersistentMemoryBackend`
    via structural subtyping.  All data is lost on process exit.
    """

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    async def store(
        self,
        name: str,
        content: str,
        *,
        memory_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Store content under *name* and return the record id."""
        now = datetime.now(timezone.utc).isoformat()
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            name=name,
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._records[name] = record
        return record.id

    async def recall(self, name: str) -> MemoryRecord | None:
        """Recall a memory by name, or ``None`` if not found."""
        return self._records.get(name)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[MemoryRecord]:
        """Search memories by substring matching on name and content."""
        query_lower = query.lower()
        results: list[MemoryRecord] = []
        for record in self._records.values():
            if memory_type is not None and record.memory_type != memory_type:
                continue
            if (
                query_lower in record.name.lower()
                or query_lower in record.content.lower()
            ):
                results.append(record)
            if len(results) >= limit:
                break
        return results

    async def update(
        self,
        name: str,
        content: str,
        *,
        memory_type: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Overwrite the content of an existing memory."""
        record = self._records.get(name)
        if record is None:
            msg = f"No memory with name '{name}'"
            raise KeyError(msg)
        record.content = content
        record.updated_at = datetime.now(timezone.utc).isoformat()
        if memory_type is not None:
            record.memory_type = memory_type
        if metadata is not None:
            record.metadata = metadata

    async def forget(self, name: str) -> bool:
        """Remove a memory by name.  Return ``True`` if it existed."""
        if name in self._records:
            del self._records[name]
            return True
        return False

    async def list_memories(
        self, *, memory_type: str | None = None
    ) -> list[MemoryRecord]:
        """Return stored memories, optionally filtered by type."""
        if memory_type is None:
            return list(self._records.values())
        return [r for r in self._records.values() if r.memory_type == memory_type]
