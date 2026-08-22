"""loom-ai: Pluggable AI orchestration framework.

Exports ``LoomConfig`` (the central registry), all Protocol interfaces,
all data-model dataclasses, ``ConsensusEngine`` for multi-model
fan-out, ``ExecutionEngine`` for DAG-based task scheduling, and
MCP tool/resource contracts for a clean public API.
"""

from loom_ai.config import LoomConfig
from loom_ai.config_validator import Environment, LoomConfigValidator, validate_env
from loom_ai.consensus import ConsensusEngine, ConsensusResult
from loom_ai.contracts_core import ConversationManager, ModelRouter, PersistentMemoryBackend, StructuredOutputMixin
from loom_ai.contracts_execution import ExecutionObserver, ExecutionPipeline, ExecutionStep
from loom_ai.contracts_session import EvaluationHarness, SessionInitializer, WorkerRegistry
from loom_ai.contracts_workflow import ObservabilityBackend, WorkflowEngine
from loom_ai.execution import CyclicDependencyError, ExecutionEngine, LLMTaskRunner, NoopTaskRunner
from loom_ai.models import ChatMessage, ChatResponse, Chunk, Document, Embedding, ExecutionPlan, GraphEdge, GraphNode, QueueItem, ResourceContent, ResourceDefinition, SearchResult, Task, TaskStatus, ToolDefinition, ToolResult
from loom_ai.models_execution import ExecutionContext, ExecutionResult, ExecutionStatus, StepResult, StepStatus
from loom_ai.protocols import EmbeddingBackend, GraphBackend, IdempotentStore, LLMBackend, QueueBackend, ResourceProvider, SearchBackend, SecretsBackend, StorageBackend, TaskRunner, ToolProvider
from loom_ai.workflow_lang import WorkflowBuilder, WorkflowDefinition, WorkflowNode, WorkflowValidationError

__all__ = [
    "LoomConfig", "ConsensusEngine", "ConsensusResult", "ChatMessage", "ChatResponse", "Chunk", "Document", "Embedding", "ExecutionPlan", "GraphEdge", "GraphNode", "QueueItem", "ResourceContent", "ResourceDefinition", "SearchResult", "Task", "TaskStatus", "ToolDefinition", "ToolResult", "CyclicDependencyError", "ExecutionEngine", "LLMTaskRunner", "NoopTaskRunner", "ExecutionContext", "ExecutionObserver", "ExecutionPipeline", "ExecutionResult", "ExecutionStatus", "ExecutionStep", "StepResult", "StepStatus", "EmbeddingBackend", "GraphBackend", "IdempotentStore", "LLMBackend", "QueueBackend", "ResourceProvider", "SearchBackend", "SecretsBackend", "StorageBackend", "TaskRunner", "ToolProvider", "Environment", "LoomConfigValidator", "validate_env", "ConversationManager", "EvaluationHarness", "ModelRouter", "ObservabilityBackend", "PersistentMemoryBackend", "SessionInitializer", "StructuredOutputMixin", "WorkerRegistry", "WorkflowEngine", "WorkflowBuilder", "WorkflowDefinition", "WorkflowNode", "WorkflowValidationError",
]

__version__ = "1.3"
