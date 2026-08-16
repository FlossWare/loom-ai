"""Protocol definitions for loom-ai backends.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required. All methods are
async. Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.config import LoomConfig
    from loom_ai.models import (
        ChatMessage,
        ChatResponse,
        Chunk,
        Document,
        Embedding,
        GraphEdge,
        GraphNode,
        QueueItem,
        ResourceContent,
        ResourceDefinition,
        SearchResult,
        Task,
        ToolDefinition,
        ToolResult,
    )


@runtime_checkable
class IdempotentStore(Protocol):
    """Marker protocol for backends with idempotent write semantics.

    Any backend that satisfies this protocol guarantees the following
    contract for every write / upsert method:

    1. **Same result** -- calling the method twice with identical arguments
       produces the same observable state as calling it once.
    2. **No duplicates** -- repeated calls never create duplicate records;
       existing records are silently replaced (upsert).
    3. **Safe retries** -- callers (HTTP handlers, queue workers, cron
       jobs) may safely retry without additional deduplication logic.

    Conforming write methods include (but are not limited to):

    - ``StorageBackend.store_document``
    - ``StorageBackend.store_chunks``
    - ``StorageBackend.store_embeddings``
    - ``SearchBackend.index``
    - ``PersistentMemoryBackend.store``
    - ``GraphBackend.add_node``

    Implementations should document any method where idempotency does
    **not** hold (e.g. ``QueueBackend.enqueue``, which intentionally
    appends duplicates).
    """

    ...


@runtime_checkable
class StorageBackend(Protocol):
    """Async persistence for documents, chunks, and embeddings.

    All ``store_*`` methods are **idempotent**: calling them twice with
    the same data produces the same observable state as calling once.
    See :class:`IdempotentStore` for the full contract.
    """

    async def store_document(self, document: Document) -> str:
        """Persist *document* and return its id.  Idempotent by document id."""
        ...

    async def get_document(self, document_id: str) -> Document | None:
        """Return a document by id, or ``None`` if not found."""
        ...

    async def list_documents(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        """Return a page of documents."""
        ...

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its dependent data."""
        ...

    async def count_documents(self) -> int:
        """Return the total number of stored documents."""
        ...

    async def store_chunks(self, document_id: str, chunks: list[Chunk]) -> int:
        """Store chunks for a document and return the count stored.

        Idempotent by chunk id -- re-storing a chunk with the same id
        replaces the previous content without creating duplicates.
        """
        ...

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        """Return all chunks for a document."""
        ...

    async def get_chunks_batch(self, chunk_ids: list[str]) -> list[Chunk]:
        """Return chunks for the given ids."""
        ...

    async def get_pending_chunks(
        self, limit: int, *, after_id: str | None = None
    ) -> list[Chunk]:
        """Return chunks that have no stored embeddings yet."""
        ...

    async def delete_chunks(self, document_id: str) -> bool:
        """Delete all chunks for a document."""
        ...

    async def count_chunks(self) -> int:
        """Return the total number of stored chunks."""
        ...

    async def store_embeddings(self, embeddings: list[Embedding]) -> int:
        """Persist embedding vectors and return the count stored.

        Idempotent by embedding id -- re-storing replaces previous values.
        """
        ...

    async def count_embeddings(self) -> int:
        """Return the total number of stored embeddings."""
        ...


@runtime_checkable
class QueueBackend(Protocol):
    """Named task queue with enqueue/fetch/complete/requeue semantics."""

    async def enqueue(self, queue_name: str, items: list[QueueItem]) -> int:
        """Add items to the named queue."""
        ...

    async def fetch(
        self, queue_name: str, count: int, worker_id: str
    ) -> list[QueueItem]:
        """Atomically claim up to *count* items for a worker."""
        ...

    async def complete(self, queue_name: str, item_id: str) -> bool:
        """Mark an item as done."""
        ...

    async def requeue(self, queue_name: str, items: list[QueueItem]) -> int:
        """Return items to the queue for retry."""
        ...

    async def status(self, queue_name: str) -> dict:
        """Return queue state counts."""
        ...

    async def list_queues(self) -> list[str]:
        """Return known queue names."""
        ...


@runtime_checkable
class SecretsBackend(Protocol):
    """Async secret/API-key storage."""

    async def get(self, name: str) -> str | None:
        """Return the secret value for *name*, or ``None``."""
        ...

    async def set(self, name: str, value: str) -> bool:
        """Store or overwrite a secret."""
        ...

    async def list_names(self) -> list[str]:
        """Return secret names without exposing values."""
        ...

    async def delete(self, name: str) -> bool:
        """Remove a secret."""
        ...


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Provider-agnostic vector-embedding generation."""

    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...

    async def embed_single(self, text: str, *, model: str | None = None) -> list[float]:
        """Embed exactly one text."""
        ...

    async def available_models(self) -> list[str]:
        """Return model identifiers available through this backend."""
        ...

    async def dimensions(self, *, model: str | None = None) -> int:
        """Return vector dimensionality."""
        ...


@runtime_checkable
class SearchBackend(Protocol):
    """Full-text, semantic, and hybrid search over indexed chunks."""

    async def index(
        self,
        chunk: Chunk,
        vector: list[float] | None = None,
        *,
        document_title: str = "",
        source: str = "",
    ) -> bool:
        """Index a chunk.  Idempotent by chunk id (upsert semantics).

        Returns ``True`` if new data was written, ``False`` if the chunk
        was already indexed with identical content.  Re-indexing with
        updated content replaces the previous entry.
        """
        ...

    async def text_search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        """Return text-search matches."""
        ...

    async def semantic_search(
        self, vector: list[float], *, limit: int = 10
    ) -> list[SearchResult]:
        """Return nearest semantic matches."""
        ...

    async def hybrid_search(
        self,
        query: str,
        vector: list[float],
        *,
        limit: int = 10,
        text_weight: float = 0.5,
    ) -> list[SearchResult]:
        """Combine text and semantic search."""
        ...

    async def delete_by_document(self, document_id: str) -> int:
        """Remove all indexed data for a document."""
        ...


@runtime_checkable
class GraphBackend(Protocol):
    """Optional knowledge-graph storage."""

    async def add_node(self, node: GraphNode) -> str:
        """Persist a graph node."""
        ...

    async def get_node(self, node_id: str) -> GraphNode | None:
        """Return a graph node by id."""
        ...

    async def add_edge(self, edge: GraphEdge) -> str:
        """Persist a graph edge."""
        ...

    async def get_neighbors(
        self, node_id: str, *, edge_label: str | None = None
    ) -> list[GraphNode]:
        """Return connected nodes."""
        ...

    async def traverse(
        self,
        start_id: str,
        *,
        edge_label: str | None = None,
        depth: int = 1,
    ) -> list[GraphNode]:
        """Traverse the graph from a starting node."""
        ...

    async def delete_node(self, node_id: str) -> bool:
        """Delete a node and incident edges."""
        ...

    async def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge."""
        ...


@runtime_checkable
class LLMBackend(Protocol):
    """Provider-agnostic chat completion interface.

    Multi-model consensus is handled by
    :class:`~loom_ai.consensus.ConsensusEngine`, which wraps any
    ``LLMBackend`` instance.
    """

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Send a chat completion request."""
        ...

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream content deltas."""
        ...

    async def list_models(self) -> list[str]:
        """Return available model identifiers."""
        ...


@runtime_checkable
class ToolProvider(Protocol):
    """Transport-neutral Loom contract for MCP-shaped tool access."""

    async def list_tools(self) -> list[ToolDefinition]:
        """Return available tool definitions."""
        ...

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        """Invoke a tool and return a ToolResult."""
        ...


@runtime_checkable
class ResourceProvider(Protocol):
    """Transport-neutral Loom contract for MCP-shaped resources."""

    async def list_resources(self) -> list[ResourceDefinition]:
        """Return available resource definitions."""
        ...

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a resource by URI."""
        ...


@runtime_checkable
class TaskRunner(Protocol):
    """Strategy for executing a single task within Loom's engine."""

    async def run(self, task: Task, config: LoomConfig) -> Any:
        """Execute a task and return an arbitrary result."""
        ...
