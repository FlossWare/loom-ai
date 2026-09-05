"""Data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Every backend protocol references these types for its method
signatures.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


@dataclass
class Document:
    """A source document ingested into the system."""

    id: str
    title: str
    content: str
    url: str = ""
    category: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Chunk:
    """A segment of a document prepared for embedding and retrieval."""

    id: str
    document_id: str
    content: str
    chunk_index: int
    content_hash: str = ""
    token_count: int = 0
    start_offset: int = 0
    end_offset: int = 0
    metadata: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    @property
    def sequence(self) -> int:
        """Alias for chunk_index to support sequence semantics from FlossWare/chunking."""
        return self.chunk_index


@dataclass
class Embedding:
    """A vector representation of a text chunk."""

    id: str
    chunk_id: str
    vector: list[float]
    model: str = ""
    provider: str = ""
    dimensions: int = 0


@dataclass
class QueueItem:
    """An item in a named task queue."""

    id: str
    payload: dict = field(default_factory=dict)
    enqueued_at: float = 0.0
    worker_id: str | None = None


@dataclass
class SearchResult:
    """A single result from a text, semantic, or hybrid search."""

    chunk_id: str
    content: str
    score: float
    document_title: str = ""
    source: str = ""


@dataclass
class ChatMessage:
    """A single message in an LLM chat conversation."""

    role: str
    content: str


@dataclass
class ChatResponse:
    """Response from an LLM chat completion request."""

    content: str
    model: str = ""
    provider: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class GraphNode:
    """A node in a knowledge graph."""

    id: str
    label: str
    properties: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in a knowledge graph."""

    id: str
    source: str
    target: str
    label: str
    properties: dict = field(default_factory=dict)


# ── MCP contract models ─────────────────────────────────────────────────


@dataclass
class ToolDefinition:
    """JSON-Schema-shaped contract for a callable MCP tool.

    ``input_schema`` is an object schema whose ``properties`` and
    ``required`` members describe the arguments accepted by the tool.
    Loom intentionally models the contract without implementing an MCP
    transport or server.
    """

    name: str
    description: str
    input_schema: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


@dataclass
class ToolResult:
    """Result returned after invoking an MCP tool."""

    tool_name: str
    output: object = None
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class ResourceDefinition:
    """Descriptor for a readable MCP resource."""

    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None


@dataclass
class ResourceContent:
    """Content payload returned when reading an MCP resource."""

    uri: str
    content: str | bytes = ""
    mime_type: str = "text/plain"


# ── Execution Engine ────────────────────────────────────────────────────


class TaskStatus(enum.Enum):
    """Lifecycle states for a task in an execution plan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A unit of work within an execution plan."""

    id: str
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    error: str = ""
    retries_remaining: int = 0
    timeout_seconds: float = 0.0
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class ExecutionPlan:
    """An ordered collection of tasks with dependency relationships."""

    id: str
    tasks: list[Task] = field(default_factory=list)
    created_at: str = ""
