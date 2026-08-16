"""Phase 1 protocol contracts for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All I/O methods
are async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 1 covers seven contract areas:

- **StructuredOutputMixin** -- structured / schema-validated chat (#89)
- **ConversationManager** -- multi-turn session management (#90)
- **PersistentMemoryBackend** -- named memory storage and recall (#91)
- **ModelRouter** -- provider-aware model routing and fallback (#92)
- **ExecutionPattern** -- pluggable multi-model execution strategies (#93)
- **ChunkingStrategy / KnowledgePipeline** -- RAG ingestion and query (#94)
- **StreamEvent / ToolCallDelta models** -- rich streaming events (#95)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models import ChatMessage
    from loom_ai.models_phase1 import (
        MemoryRecord,
        ModelInfo,
        PatternResult,
        ProviderStatus,
        RetrievalResult,
        StructuredResponse,
    )
    from loom_ai.protocols import LLMBackend


# ── Structured Output (#89) ───────────────────────────────────────────


@runtime_checkable
class StructuredOutputMixin(Protocol):
    """Mixin protocol for LLM backends that support schema-validated output.

    Implementations should attempt up to *max_retries* completions when
    the response does not conform to *schema*.
    """

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict | None = None,
        tools: list[dict] | None = None,
        response_format: str = "text",
        max_retries: int = 3,
        **kwargs: Any,
    ) -> StructuredResponse:
        """Send a chat completion request with structured output constraints."""
        ...


# ── Conversation Management (#90) ─────────────────────────────────────


@runtime_checkable
class ConversationManager(Protocol):
    """Multi-turn conversation session management.

    Sessions hold ordered message histories with optional token-budget
    compression and fork support.
    """

    async def create_session(self, *, metadata: dict | None = None) -> str:
        """Create a new conversation session and return its id."""
        ...

    async def add_message(self, session_id: str, message: ChatMessage) -> None:
        """Append a message to the session history."""
        ...

    async def get_messages(
        self, session_id: str, *, max_tokens: int | None = None
    ) -> list[ChatMessage]:
        """Return messages for the session, optionally trimmed to a token budget."""
        ...

    async def compress(self, session_id: str, *, target_tokens: int) -> None:
        """Compress the session history to fit within *target_tokens*."""
        ...

    async def fork(self, session_id: str) -> str:
        """Create a copy of the session and return the new session id."""
        ...

    async def export_transcript(self, session_id: str) -> list[dict]:
        """Export the full session transcript as a list of plain dicts."""
        ...


# ── Persistent Memory (#91) ───────────────────────────────────────────


@runtime_checkable
class PersistentMemoryBackend(Protocol):
    """Named, typed memory storage for long-term recall across sessions."""

    async def store(
        self,
        name: str,
        content: str,
        *,
        memory_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Store content under *name* and return the record id."""
        ...

    async def recall(self, name: str) -> MemoryRecord | None:
        """Recall a memory by name, or ``None`` if not found."""
        ...

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[MemoryRecord]:
        """Search memories by query text with optional type filter."""
        ...

    async def update(self, name: str, content: str) -> None:
        """Overwrite the content of an existing memory."""
        ...

    async def forget(self, name: str) -> bool:
        """Remove a memory by name.  Return ``True`` if it existed."""
        ...

    async def list_memories(
        self, *, memory_type: str | None = None
    ) -> list[MemoryRecord]:
        """Return stored memories, optionally filtered by type."""
        ...


# ── Model Router (#92) ────────────────────────────────────────────────


@runtime_checkable
class ModelRouter(Protocol):
    """Provider-aware routing with fallback, health checks, and cost estimation."""

    async def route(self, model: str, *, fallback: bool = True) -> LLMBackend:
        """Resolve *model* to an ``LLMBackend``, falling back if unavailable."""
        ...

    async def register_provider(
        self,
        name: str,
        backend: LLMBackend,
        *,
        models: list[str],
        priority: int = 0,
    ) -> None:
        """Register a provider backend with its supported models."""
        ...

    async def list_available_models(self) -> list[ModelInfo]:
        """Return metadata for all currently reachable models."""
        ...

    async def provider_health(self) -> dict[str, ProviderStatus]:
        """Return per-provider health information."""
        ...

    async def estimate_cost(self, model: str, tokens: int) -> float:
        """Return the estimated cost in USD for *tokens* on *model*."""
        ...


# ── Execution Patterns (#93) ──────────────────────────────────────────


@runtime_checkable
class ExecutionPattern(Protocol):
    """Pluggable multi-model execution strategy.

    Supports patterns such as consensus, cascade, and map-reduce.
    """

    async def execute(
        self,
        task: str,
        *,
        models: list[str],
        router: ModelRouter | None = None,
        backend: LLMBackend | None = None,
        config: dict | None = None,
    ) -> PatternResult:
        """Run the pattern against *task* using the given *models*."""
        ...


# ── RAG: Chunking & Knowledge Pipeline (#94) ──────────────────────────


@runtime_checkable
class ChunkingStrategy(Protocol):
    """Synchronous text-chunking strategy for RAG ingestion."""

    def chunk(
        self,
        content: str,
        *,
        max_tokens: int = 512,
        overlap: int = 50,
    ) -> list[str]:
        """Split *content* into overlapping token-bounded chunks."""
        ...


@runtime_checkable
class KnowledgePipeline(Protocol):
    """End-to-end RAG ingestion and retrieval pipeline."""

    async def ingest(
        self,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> str:
        """Ingest *content* into the knowledge base and return a document id."""
        ...

    async def query(
        self,
        question: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Retrieve the most relevant chunks for *question*."""
        ...


# ── Streaming Events (#95) ────────────────────────────────────────────
#
# The StreamEvent and ToolCallDelta models are defined in
# ``models_phase1.py``.  They enable a richer streaming contract where
# ``LLMBackend.chat_stream`` would return ``AsyncIterator[StreamEvent]``
# instead of ``AsyncIterator[str]``.
#
# The existing ``LLMBackend`` protocol is intentionally NOT modified
# here; the new signature is:
#
#     async def chat_stream(
#         self,
#         messages: list[ChatMessage],
#         *,
#         model: str | None = None,
#         temperature: float = 0.7,
#         max_tokens: int | None = None,
#     ) -> AsyncIterator[StreamEvent]:
#         ...
#
# This change will be applied to ``protocols.py`` once Phase 1
# implementations adopt the new models.
