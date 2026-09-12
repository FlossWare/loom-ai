"""loom-ai: intent-driven AI orchestration runtime.

The canonical execution model is deliberately small:

    Intent -> Worker -> result
                 ^
               Arbiter

``Intent`` describes desired outcome without prescribing execution.
``Worker`` is the fundamental executable abstraction. ``Arbiter`` is a
composable Worker that coordinates other Workers.

The older contract facade and execution classes remain temporarily available
for compatibility while the repository is consolidated around these
primitives. They are not the preferred architecture for new code.
"""

from loom_ai.arbiter import Arbiter, ArbiterDecision, WorkerEvaluation
from loom_ai.config import LoomConfig
from loom_ai.config_validator import Environment, LoomConfigValidator, validate_env
from loom_ai.consensus import ConsensusEngine, ConsensusResult
from loom_ai.contracts_core import (
    ConversationManager,
    ModelRouter,
    PersistentMemoryBackend,
    StructuredOutputMixin,
)
from loom_ai.contracts_execution import ExecutionObserver, ExecutionPipeline, ExecutionStep
from loom_ai.contracts_session import EvaluationHarness, SessionInitializer, WorkerRegistry
from loom_ai.contracts_workflow import ObservabilityBackend, WorkflowEngine
from loom_ai.execution import CyclicDependencyError, ExecutionEngine, LLMTaskRunner, NoopTaskRunner
from loom_ai.intent import Intent, IntentParseError
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
from loom_ai.worker import Worker, WorkerContext, WorkerResult, WorkerStatus

__all__ = [
    "Arbiter",
    "ArbiterDecision",
    "WorkerEvaluation",
    "Intent",
    "IntentParseError",
    "Worker",
    "WorkerContext",
    "WorkerResult",
    "WorkerStatus",
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
    "Environment",
    "LoomConfigValidator",
    "validate_env",
    "ConversationManager",
    "EvaluationHarness",
    "ModelRouter",
    "ObservabilityBackend",
    "PersistentMemoryBackend",
    "SessionInitializer",
    "StructuredOutputMixin",
    "WorkerRegistry",
    "WorkflowEngine",
]

__version__ = "1.2"
