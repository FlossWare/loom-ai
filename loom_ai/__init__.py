"""loom-ai: Pluggable AI orchestration framework.

Exports ``LoomConfig`` (the central registry), all Protocol interfaces,
and all data-model dataclasses for a clean public API.

Quick start::

    from loom_ai import LoomConfig

    # Zero-config: all in-memory / no-op backends
    cfg = LoomConfig.from_env()

    # Or inject your own backends
    cfg = LoomConfig(
        storage=my_pg_storage,
        queue=my_redis_queue,
        secrets=my_vault_secrets,
        embedding=my_openai_embeddings,
        search=my_pg_search,
        graph=my_orientdb_graph,
        llm=my_http_llm,
    )
"""

from loom_ai.config import LoomConfig
from loom_ai.consensus import ConsensusEngine, ConsensusResult
from loom_ai.models import (
    ChatMessage,
    ChatResponse,
    Chunk,
    Document,
    Embedding,
    GraphEdge,
    GraphNode,
    QueueItem,
    SearchResult,
)
from loom_ai.protocols import (
    EmbeddingBackend,
    GraphBackend,
    LLMBackend,
    QueueBackend,
    SearchBackend,
    SecretsBackend,
    StorageBackend,
)

__all__ = [
    # Registry
    "LoomConfig",
    # Consensus
    "ConsensusEngine",
    "ConsensusResult",
    # Data models
    "ChatMessage",
    "ChatResponse",
    "Chunk",
    "Document",
    "Embedding",
    "GraphEdge",
    "GraphNode",
    "QueueItem",
    "SearchResult",
    # Protocols
    "EmbeddingBackend",
    "GraphBackend",
    "LLMBackend",
    "QueueBackend",
    "SearchBackend",
    "SecretsBackend",
    "StorageBackend",
]

__version__ = "1.1"
