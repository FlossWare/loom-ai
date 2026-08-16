"""loom-ai: Pluggable AI orchestration framework.

Exports ``LoomConfig`` (the central registry), all Protocol interfaces,
all data-model dataclasses, ``ConsensusEngine`` for multi-model
fan-out, ``ExecutionEngine`` for DAG-based task scheduling, and
MCP tool/resource contracts for a clean public API.

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
from loom_ai.execution import (
    CyclicDependencyError,
    ExecutionEngine,
    LLMTaskRunner,
    NoopTaskRunner,
)
from loom_ai.models import (
    ChatMessage,
    ChatResponse,
    Chunk,
    Document,
    Embedding,
    ExecutionPlan,
    GraphEdge,
    GraphNode,
    QueueItem,
    ResourceContent,
    ResourceDefinition,
    SearchResult,
    Task,
    TaskStatus,
    ToolDefinition,
    ToolResult,
)
from loom_ai.protocols import (
    EmbeddingBackend,
    GraphBackend,
    IdempotentStore,
    LLMBackend,
    QueueBackend,
    ResourceProvider,
    SearchBackend,
    SecretsBackend,
    StorageBackend,
    TaskRunner,
    ToolProvider,
)

__all__ = [
    "LoomConfig",
    "ConsensusEngine",
    "ConsensusResult",
    "ChatMessage",
    "ChatResponse",
    "Chunk",
    "Document",
    "Embedding",
    "ExecutionPlan",
    "GraphEdge",
    "GraphNode",
    "QueueItem",
    "ResourceContent",
    "ResourceDefinition",
    "SearchResult",
    "Task",
    "TaskStatus",
    "ToolDefinition",
    "ToolResult",
    "CyclicDependencyError",
    "ExecutionEngine",
    "LLMTaskRunner",
    "NoopTaskRunner",
    "EmbeddingBackend",
    "GraphBackend",
    "IdempotentStore",
    "LLMBackend",
    "QueueBackend",
    "ResourceProvider",
    "SearchBackend",
    "SecretsBackend",
    "StorageBackend",
    "TaskRunner",
    "ToolProvider",
]

__version__ = "1.2"
