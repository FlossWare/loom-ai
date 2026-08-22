"""loom-ai: Pluggable AI orchestration framework.

Exports ``LoomConfig`` (the central registry), all Protocol interfaces,
all data-model dataclasses, ``ConsensusEngine`` for multi-model
fan-out, ``ExecutionEngine`` for DAG-based task scheduling, and
MCP tool/resource contracts for a clean public API.

Quick start::

    import asyncio
    from loom_ai import LoomConfig

    # Zero-config: all in-memory / no-op backends
    cfg = asyncio.run(LoomConfig.from_env())

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

For the full set of 81 protocol contracts, use the consolidated
facade::

    from loom_ai.contracts import StorageBackend, WorkflowEngine, ...

See ``docs/contracts.md`` for the canonical contract inventory.
"""

from loom_ai.config import LoomConfig
from loom_ai.config_validator import (
    Environment,
    LoomConfigValidator,
    validate_env,
)
from loom_ai.consensus import ConsensusEngine, ConsensusResult
from loom_ai.contracts_core import (
    ConversationManager,
    ModelRouter,
    PersistentMemoryBackend,
    StructuredOutputMixin,
)
from loom_ai.contracts_execution import (
    ExecutionObserver,
    ExecutionPipeline,
    ExecutionStep,
)
from loom_ai.contracts_session import (
    EvaluationHarness,
    SessionInitializer,
    WorkerRegistry,
)
from loom_ai.contracts_workflow import (
    ObservabilityBackend,
    WorkflowEngine,
)
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
from loom_ai.models_execution import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    StepResult,
    StepStatus,
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
from loom_ai.workflow_lang import (
    WorkflowBuilder,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowValidationError,
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
    "ExecutionContext",
    "ExecutionObserver",
    "ExecutionPipeline",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutionStep",
    "StepResult",
    "StepStatus",
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
    # Configuration validation
    "Environment",
    "LoomConfigValidator",
    "validate_env",
    # Most-used advanced contracts
    "ConversationManager",
    "EvaluationHarness",
    "ModelRouter",
    "ObservabilityBackend",
    "PersistentMemoryBackend",
    "SessionInitializer",
    "StructuredOutputMixin",
    "WorkerRegistry",
    "WorkflowEngine",
    # Declarative workflow language
    "WorkflowBuilder",
    "WorkflowDefinition",
    "WorkflowNode",
    "WorkflowValidationError",
]

__version__ = "1.3"
