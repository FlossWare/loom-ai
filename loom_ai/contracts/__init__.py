"""Consolidated re-export facade for all loom-ai protocol contracts.

This module is the **stable public import path** for every
``@runtime_checkable`` Protocol in the framework.  All 81 contracts are
re-exported here so that consumers can write::

    from loom_ai.contracts import StorageBackend, WorkflowEngine, ...

The underlying domain modules (``contracts_core``, ``contracts_workflow``,
etc., plus ``contracts_api`` and ``protocols``) are implementation
artifacts and may be reorganised in future releases.  Import from this
facade to avoid breakage.

Protocols use structural subtyping -- implementations do **not** need
to import or inherit from these classes.  Any object whose methods
match the protocol signature satisfies the contract at runtime.
"""

from __future__ import annotations

# ── Agent: agent loop, recipe, ACP, context assembler, ──────────────
# ──        trajectory, environment, capability registry ──────────────
from loom_ai.contracts_agent import (
    ACPAdapter,
    AgentCapabilityRegistry,
    AgentEnvironment,
    AgentLoop,
    ContextAssembler,
    RecipeExecutor,
    TrajectoryStore,
)

# ── REST API contracts (contracts_api.py) ────────────────────────────
from loom_ai.contracts_api import (
    ErrorHandler,
    Middleware,
    RequestLifecycle,
)

# ── Capability: eval capability, capability selector, interaction ────
# ──             evaluator, skill estimator, evaluation env,       ────
# ──             tournament, inference optimizer, output normalizer ────
from loom_ai.contracts_capability import (
    CapabilitySelector,
    ConsensusStrategy,
    EvalCapabilityRegistry,
    EvaluationEnvironment,
    InferenceOptimizer,
    InteractionEvaluator,
    OutputNormalizer,
    SkillEstimator,
    TournamentRunner,
)

# ── Context: model evaluation, canonical source, context ────────────
# ──          compressor, prompt cache, pluggable runtimes, ──────────
# ──          context engine, capability backend, evaluation ─────────
# ──          engine, health check, request validation       ─────────
from loom_ai.contracts_context import (
    CanonicalSourceIndex,
    CapabilityBackend,
    ContextCompressor,
    ContextEngine,
    EvaluationEngine,
    HealthCheckPolicy,
    ModelEvaluationCandidate,
    PluggableAgentRuntime,
    PromptCacheOptimizer,
    RequestValidator,
)

# ── Core: Structured output, conversation, memory, routing, ─────────
# ──       patterns, RAG, streaming                           ─────────
from loom_ai.contracts_core import (
    ChunkingStrategy,
    ConversationManager,
    ExecutionPattern,
    KnowledgePipeline,
    ModelRouter,
    PersistentMemoryBackend,
    StructuredOutputMixin,
)

# ── Execution protocols (contracts_execution.py) ─────────────────────
from loom_ai.contracts_execution import (
    ExecutionObserver,
    ExecutionPipeline,
    ExecutionStep,
)

# ── Graph: Knowledge graph, temporal, GraphRAG, external, ───────────
# ──        belief management                              ───────────
from loom_ai.contracts_graph import (
    BeliefManager,
    ExternalGraphAdapter,
    GraphRetriever,
    KnowledgeGraph,
    TemporalKnowledgeStore,
)

# ── Inference: eval suite, telemetry, inference routing, agent ───────
# ──            lifecycle, agent memory, output validation,     ───────
# ──            security, program optimization                  ───────
from loom_ai.contracts_inference import (
    AgentLifecycleRuntime,
    AgentMemory,
    EvalSuite,
    GenAITelemetry,
    InferenceRouter,
    OutputValidator,
    ProgramOptimizer,
    SecurityGate,
)

# ── Provider: provider registry, capability registry, policy, ───────
# ──           catalog synchronization                         ───────
from loom_ai.contracts_provider import (
    CatalogSynchronizer,
    PolicyRegistry,
    ProviderCapabilityRegistry,
    ProviderRegistry,
)

# ── Session: worker registry, cache, evaluation, ────────────────────
# ──          feedback loops, human-in-the-loop    ────────────────────
from loom_ai.contracts_session import (
    CachePolicy,
    EvaluationHarness,
    FeedbackLoopDetector,
    HumanInTheLoop,
    SessionInitializer,
    WorkerRegistry,
)

# ── Workflow: learning, strategy, budget, transcript, ────────────────
# ──           resilience, observability               ────────────────
from loom_ai.contracts_workflow import (
    BudgetTracker,
    LearningExtractor,
    ObservabilityBackend,
    ResiliencePolicy,
    StrategySelector,
    TranscriptStore,
    WorkflowEngine,
    WorkflowStorageBackend,
)

# ── Core protocols (protocols.py) ────────────────────────────────────
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
    # Core (protocols.py) -- 11
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
    # Core -- 7
    "ChunkingStrategy",
    "ConversationManager",
    "ExecutionPattern",
    "KnowledgePipeline",
    "ModelRouter",
    "PersistentMemoryBackend",
    "StructuredOutputMixin",
    # Workflow -- 8
    "BudgetTracker",
    "LearningExtractor",
    "ObservabilityBackend",
    "ResiliencePolicy",
    "StrategySelector",
    "TranscriptStore",
    "WorkflowEngine",
    "WorkflowStorageBackend",
    # Session -- 6
    "CachePolicy",
    "EvaluationHarness",
    "FeedbackLoopDetector",
    "HumanInTheLoop",
    "SessionInitializer",
    "WorkerRegistry",
    # Graph -- 5
    "BeliefManager",
    "ExternalGraphAdapter",
    "GraphRetriever",
    "KnowledgeGraph",
    "TemporalKnowledgeStore",
    # Inference -- 8
    "AgentLifecycleRuntime",
    "AgentMemory",
    "EvalSuite",
    "GenAITelemetry",
    "InferenceRouter",
    "OutputValidator",
    "ProgramOptimizer",
    "SecurityGate",
    # Agent -- 7
    "ACPAdapter",
    "AgentCapabilityRegistry",
    "AgentEnvironment",
    "AgentLoop",
    "ContextAssembler",
    "RecipeExecutor",
    "TrajectoryStore",
    # Provider -- 4
    "CatalogSynchronizer",
    "PolicyRegistry",
    "ProviderCapabilityRegistry",
    "ProviderRegistry",
    # Capability -- 9
    "CapabilitySelector",
    "ConsensusStrategy",
    "EvalCapabilityRegistry",
    "EvaluationEnvironment",
    "InferenceOptimizer",
    "InteractionEvaluator",
    "OutputNormalizer",
    "SkillEstimator",
    "TournamentRunner",
    # Context -- 10
    "CanonicalSourceIndex",
    "CapabilityBackend",
    "ContextCompressor",
    "ContextEngine",
    "EvaluationEngine",
    "HealthCheckPolicy",
    "ModelEvaluationCandidate",
    "PluggableAgentRuntime",
    "PromptCacheOptimizer",
    "RequestValidator",
    # API -- 3
    "ErrorHandler",
    "Middleware",
    "RequestLifecycle",
    # Execution -- 3
    "ExecutionObserver",
    "ExecutionPipeline",
    "ExecutionStep",
]
