"""Data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Every backend protocol references these types for its method
signatures.
"""

from __future__ import annotations

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
