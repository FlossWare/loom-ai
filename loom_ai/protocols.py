"""Protocol definitions for loom-ai backends.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All methods are
async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Protocol,
    runtime_checkable,
)

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


# ── StorageBackend ───────────────────────────────────────────────────────


@runtime_checkable
class StorageBackend(Protocol):
    """Async persistence for documents, chunks, and embeddings.

    Handles CRUD plus counting and cursor-based retrieval of chunks
    that have not yet been embedded (``get_pending_chunks``).

    Crush deployment  -> MemoryStorageBackend (dict-backed)
    Claude deployment -> PostgreSQL backend
    """

    # -- Documents --------------------------------------------------------

    async def store_document(self, document: Document) -> str:
        """Persist *document* and return its id."""
        ...

    async def get_document(self, document_id: str) -> Document | None:
        """Return a document by id, or ``None`` if not found."""
        ...

    async def list_documents(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        """Return a page of documents in insertion order."""
        ...

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and cascade to its chunks and embeddings.

        Returns ``True`` if the document existed.
        """
        ...

    async def count_documents(self) -> int:
        """Return the total number of stored documents."""
        ...

    # -- Chunks -----------------------------------------------------------

    async def store_chunks(
        self, document_id: str, chunks: list[Chunk]
    ) -> int:
        """Store chunks for a document and return the count stored."""
        ...

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        """Return all chunks for a document, ordered by ``chunk_index``."""
        ...

    async def get_chunks_batch(self, chunk_ids: list[str]) -> list[Chunk]:
        """Return chunks for the given ids (order not guaranteed)."""
        ...

    async def get_pending_chunks(
        self, limit: int, *, after_id: str | None = None
    ) -> list[Chunk]:
        """Return chunks that have no stored embeddings yet.

        Uses cursor-based pagination: when *after_id* is provided,
        results start after that chunk id in insertion order.
        """
        ...

    async def delete_chunks(self, document_id: str) -> bool:
        """Delete all chunks for a document.  Returns ``True`` if any existed."""
        ...

    async def count_chunks(self) -> int:
        """Return the total number of stored chunks."""
        ...

    # -- Embeddings -------------------------------------------------------

    async def store_embeddings(self, embeddings: list[Embedding]) -> int:
        """Persist embedding vectors and return the count stored."""
        ...

    async def count_embeddings(self) -> int:
        """Return the total number of stored embeddings."""
        ...


# ── QueueBackend ─────────────────────────────────────────────────────────


@runtime_checkable
class QueueBackend(Protocol):
    """Named task queue with enqueue / fetch / complete / requeue semantics.

    Items transition through states: **queued -> processing -> done**.

    Crush deployment  -> MemoryQueueBackend (collections.deque)
    Claude deployment -> Redis lists + sorted sets
    """

    async def enqueue(self, queue_name: str, items: list[QueueItem]) -> int:
        """Add *items* to the named queue and return the count enqueued."""
        ...

    async def fetch(
        self, queue_name: str, count: int, worker_id: str
    ) -> list[QueueItem]:
        """Atomically move up to *count* items to processing state.

        Each claimed item has its ``worker_id`` set.  The returned list
        may be shorter than *count* when the queue is shallow.
        """
        ...

    async def complete(self, queue_name: str, item_id: str) -> bool:
        """Mark an item as done and remove it.

        Returns ``True`` if the item was found in processing state.
        """
        ...

    async def requeue(self, queue_name: str, items: list[QueueItem]) -> int:
        """Return items from processing back to queued state for retry.

        The ``worker_id`` field on each item is cleared upon requeue.
        """
        ...

    async def status(self, queue_name: str) -> dict:
        """Return ``{"queued": int, "processing": int}`` for the queue."""
        ...

    async def list_queues(self) -> list[str]:
        """Return all known queue names, sorted alphabetically."""
        ...


# ── SecretsBackend ───────────────────────────────────────────────────────


@runtime_checkable
class SecretsBackend(Protocol):
    """Async secret / API-key storage.

    Crush deployment  -> EnvSecretsBackend (os.environ + .env file)
    Claude deployment -> a PostgreSQL or HashiCorp Vault backend
    """

    async def get(self, name: str) -> str | None:
        """Return the secret value for *name*, or ``None``."""
        ...

    async def set(self, name: str, value: str) -> bool:
        """Store or overwrite a secret.  Return ``True`` on success."""
        ...

    async def list_names(self) -> list[str]:
        """Return the names of every stored secret (values NOT exposed)."""
        ...

    async def delete(self, name: str) -> bool:
        """Remove a secret.  Return ``True`` if it existed and was deleted."""
        ...


# ── EmbeddingBackend ─────────────────────────────────────────────────────


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Vector-embedding generation (text -> float vectors).

    Implementations wrap a specific provider (sentence-transformers,
    OpenAI, Voyage, etc.).  The protocol is provider-agnostic.

    Crush deployment  -> NoopEmbeddingBackend (zero vectors)
    Claude deployment -> a real provider backend
    """

    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float]]:
        """Return one embedding vector per input text.

        All returned vectors have the same dimensionality.
        """
        ...

    async def embed_single(
        self, text: str, *, model: str | None = None
    ) -> list[float]:
        """Convenience: embed exactly one text and return its vector."""
        ...

    async def available_models(self) -> list[str]:
        """Return the model identifiers this backend can serve."""
        ...

    async def dimensions(self, *, model: str | None = None) -> int:
        """Return the vector dimensionality for *model* (or the default)."""
        ...


# ── SearchBackend ────────────────────────────────────────────────────────


@runtime_checkable
class SearchBackend(Protocol):
    """Full-text, semantic, and hybrid search over indexed chunks.

    The search backend maintains its own index.  Chunks (and optionally
    their embedding vectors) are added via ``index``.

    Crush deployment  -> MemorySearchBackend (substring + brute-force cosine)
    Claude deployment -> PostgreSQL full-text + pgvector ANN
    """

    async def index(
        self,
        chunk: Chunk,
        vector: list[float] | None = None,
        *,
        document_title: str = "",
        source: str = "",
    ) -> bool:
        """Index a chunk so it becomes searchable.

        *vector* is optional -- pass it to enable semantic search for
        this chunk.  Returns ``True`` if the chunk was newly indexed,
        ``False`` if it was already present (idempotent by ``chunk.id``).
        """
        ...

    async def text_search(
        self, query: str, *, limit: int = 10
    ) -> list[SearchResult]:
        """Return chunks matching *query* via full-text (or substring) search."""
        ...

    async def semantic_search(
        self, vector: list[float], *, limit: int = 10
    ) -> list[SearchResult]:
        """Return chunks nearest to *vector* by cosine similarity."""
        ...

    async def hybrid_search(
        self,
        query: str,
        vector: list[float],
        *,
        limit: int = 10,
        text_weight: float = 0.5,
    ) -> list[SearchResult]:
        """Combine text and semantic search with weighted fusion.

        *text_weight* is in ``[0.0, 1.0]``; the semantic weight is
        ``1.0 - text_weight``.
        """
        ...

    async def delete_by_document(self, document_id: str) -> int:
        """Remove all indexed data for a document.  Return count removed."""
        ...


# ── GraphBackend ─────────────────────────────────────────────────────────


@runtime_checkable
class GraphBackend(Protocol):
    """Knowledge-graph storage for entity / relationship queries.

    Optional -- the crush deployment disables it via
    ``DisabledGraphBackend``.  The claude deployment uses OrientDB.
    """

    async def add_node(self, node: GraphNode) -> str:
        """Persist *node* and return its id."""
        ...

    async def get_node(self, node_id: str) -> GraphNode | None:
        """Return the node with *node_id*, or ``None``."""
        ...

    async def add_edge(self, edge: GraphEdge) -> str:
        """Persist *edge* and return its id."""
        ...

    async def get_neighbors(
        self, node_id: str, *, edge_label: str | None = None
    ) -> list[GraphNode]:
        """Return nodes connected to *node_id*.

        If *edge_label* is given, only traverse edges with that label.
        """
        ...

    async def traverse(
        self,
        start_id: str,
        *,
        edge_label: str | None = None,
        depth: int = 1,
    ) -> list[GraphNode]:
        """BFS traversal from *start_id* up to the given *depth*."""
        ...

    async def delete_node(self, node_id: str) -> bool:
        """Delete the node and all its incident edges.

        Returns ``True`` if the node existed.
        """
        ...

    async def delete_edge(self, edge_id: str) -> bool:
        """Delete the edge.  Returns ``True`` if it existed."""
        ...


# ── LLMBackend ───────────────────────────────────────────────────────────


@runtime_checkable
class LLMBackend(Protocol):
    """Chat completion interface for LLM inference.

    Supports single-model chat, streaming, and model listing.
    Multi-model consensus is handled by
    :class:`~loom_ai.consensus.ConsensusEngine`, which wraps any
    ``LLMBackend`` instance.

    Crush deployment  -> HttpLLMBackend (urllib, any OpenAI-compatible API)
    Claude deployment -> same, or a routing layer
    """

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Send a chat completion request and return the full response."""
        ...

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a chat completion, yielding content-delta strings."""
        ...

    async def list_models(self) -> list[str]:
        """Return sorted model identifiers available through this backend."""
        ...


# ── ToolProvider (MCP) ──────────────────────────────────────────────────


@runtime_checkable
class ToolProvider(Protocol):
    """MCP tool provider: list available tools and invoke them by name.

    Each tool is described by a ``ToolDefinition`` (JSON-Schema-style
    parameter spec) and returns a ``ToolResult`` on invocation.

    Crush deployment  -> MemoryToolProvider (dict-backed callables)
    Claude deployment -> an MCP server adapter
    """

    async def list_tools(self) -> list[ToolDefinition]:
        """Return definitions for every tool this provider exposes."""
        ...

    async def call_tool(
        self, name: str, arguments: dict
    ) -> ToolResult:
        """Invoke the tool identified by *name* with the given arguments.

        Implementations must return a ``ToolResult`` with ``error`` set
        (rather than raising) when the tool itself fails.
        """
        ...


# ── ResourceProvider (MCP) ──────────────────────────────────────────────


@runtime_checkable
class ResourceProvider(Protocol):
    """MCP resource provider: list and read data sources.

    Resources are identified by URI and return typed content payloads.

    Crush deployment  -> MemoryResourceProvider (dict-backed)
    Claude deployment -> an MCP server adapter
    """

    async def list_resources(self) -> list[ResourceDefinition]:
        """Return definitions for every resource this provider exposes."""
        ...

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read the content of the resource at *uri*.

        Raises ``KeyError`` when the URI is not found.
        """
        ...


# -- TaskRunner ──────────────────────────────────────────────────────────


@runtime_checkable
class TaskRunner(Protocol):
    """Executes a single task within the orchestration engine.

    Implementations define *how* a task runs (LLM call, tool
    invocation, pass-through, etc.).  The execution engine calls
    ``run`` and maps the return value into ``task.output_data``.
    """

    async def run(self, task: Task, config: LoomConfig) -> Any:
        """Execute *task* and return an arbitrary result.

        The engine stores ``dict`` results directly as
        ``output_data``; non-dict results are wrapped in
        ``{"result": value}``.
        """
        ...
