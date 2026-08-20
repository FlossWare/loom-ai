"""Phase 1 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  These models support the Phase 1 protocol contracts defined
in ``contracts_core.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StructuredResponse:
    """Response from a structured-output chat completion."""

    content: str
    parsed: dict | None = None
    schema_valid: bool = False
    raw_text: str = ""
    retries_used: int = 0


@dataclass
class MemoryRecord:
    """A single record in a persistent memory store.

    Canonical memory model for loom-ai.  Covers session-scoped,
    agent-scoped, and project-scoped memories through the ``scope``
    field.  Optional ``ttl_seconds`` enables time-bounded retention.
    """

    id: str
    name: str
    content: str
    memory_type: str
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    scope: str = "global"
    agent_id: str = ""
    session_id: str = ""
    ttl_seconds: int | None = None
    superseded_by: str | None = None
    confidence: float = 1.0


@dataclass
class ModelInfo:
    """Metadata describing an available LLM model."""

    model: str
    provider: str
    capabilities: list[str] = field(default_factory=list)
    context_length: int = 0
    cost_per_1k_tokens: float = 0.0


@dataclass
class ProviderStatus:
    """Health and availability status for a model provider."""

    name: str
    healthy: bool = True
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    models: list[str] = field(default_factory=list)


@dataclass
class PatternResult:
    """Result from an execution pattern run."""

    pattern: str
    results: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class RetrievalResult:
    """A single result from a knowledge pipeline query."""

    content: str
    score: float
    source: str
    chunk_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ToolCallDelta:
    """Incremental tool-call data within a streaming event."""

    id: str
    name: str
    arguments: str = ""
    complete: bool = False


@dataclass
class StreamEvent:
    """A single event emitted during streamed chat completion.

    The ``type`` field indicates the event kind (e.g. ``"content"``,
    ``"tool_call"``, ``"usage"``, ``"done"``).
    """

    type: str
    content: str | None = None
    tool_call: ToolCallDelta | None = None
    usage: dict | None = None


@dataclass
class SessionInfo:
    """Summary information about a conversation session."""

    id: str
    created_at: str = ""
    message_count: int = 0
    total_tokens: int = 0
    metadata: dict = field(default_factory=dict)
