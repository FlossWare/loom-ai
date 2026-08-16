"""Consolidated re-export facade for all loom-ai protocol contracts.

This module is the **stable public import path** for every
``@runtime_checkable`` Protocol in the framework.  All 78 contracts are
re-exported here so that consumers can write::

    from loom_ai.contracts import StorageBackend, WorkflowEngine, ...

The underlying phase modules (``contracts_phase1`` through
``contracts_phase9``, ``contracts_api``, and ``protocols``) are
implementation artifacts and may be reorganised in future releases.
Import from this facade to avoid breakage.

Protocols use structural subtyping -- implementations do **not** need
to import or inherit from these classes.  Any object whose methods
match the protocol signature satisfies the contract at runtime.
"""

from __future__ import annotations

# ── REST API contracts (contracts_api.py) ────────────────────────────
from loom_ai.contracts_api import (
    ErrorHandler,
    Middleware,
    RequestLifecycle,
)

# ── Phase 1: Structured output, conversation, memory, routing, ──────
# ──          patterns, RAG, streaming                            ──────
from loom_ai.contracts_phase1 import (
    ChunkingStrategy,
    ConversationManager,
    ExecutionPattern,
    KnowledgePipeline,
    ModelRouter,
    PersistentMemoryBackend,
    StructuredOutputMixin,
)

# ── Phase 2: Workflow, learning, strategy, budget, transcript, ───────
# ──          resilience, observability                          ───────
from loom_ai.contracts_phase2 import (
    BudgetTracker,
    LearningExtractor,
    ObservabilityBackend,
    ResiliencePolicy,
    StrategySelector,
    TranscriptStore,
    WorkflowEngine,
    WorkflowStorageBackend,
)

# ── Phase 3: Session, worker registry, cache, evaluation, ───────────
# ──          feedback loops, human-in-the-loop             ───────────
from loom_ai.contracts_phase3 import (
    CachePolicy,
    EvaluationHarness,
    FeedbackLoopDetector,
    HumanInTheLoop,
    SessionInitializer,
    WorkerRegistry,
)

# ── Phase 4: Knowledge graph, temporal, GraphRAG, external ──────────
# ──          graph, belief management                      ──────────
from loom_ai.contracts_phase4 import (
    BeliefManager,
    ExternalGraphAdapter,
    GraphRetriever,
    KnowledgeGraph,
    TemporalKnowledgeStore,
)

# ── Phase 5: Eval suite, telemetry, inference routing, agent ────────
# ──          lifecycle, agent memory, output validation,      ────────
# ──          security, program optimization                   ────────
from loom_ai.contracts_phase5 import (
    AgentLifecycleRuntime,
    AgentMemory,
    EvalSuite,
    GenAITelemetry,
    InferenceRouter,
    OutputValidator,
    ProgramOptimizer,
    SecurityGate,
)

# ── Phase 6: Agent loop, recipe, ACP, context assembler, ────────────
# ──          trajectory, environment, capability registry ────────────
from loom_ai.contracts_phase6 import (
    ACPAdapter,
    AgentCapabilityRegistry,
    AgentEnvironment,
    AgentLoop,
    ContextAssembler,
    RecipeExecutor,
    TrajectoryStore,
)

# ── Phase 7: Provider registry, capability registry, policy, ────────
# ──          catalog synchronization                          ────────
from loom_ai.contracts_phase7 import (
    CatalogSynchronizer,
    PolicyRegistry,
    ProviderCapabilityRegistry,
    ProviderRegistry,
)

# ── Phase 8: Eval capability, capability selector, interaction ──────
# ──          evaluator, skill estimator, evaluation env,        ──────
# ──          tournament, inference optimizer, output normalizer, ─────
# ──          consensus strategy                                  ─────
from loom_ai.contracts_phase8 import (
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

# ── Phase 9: Model evaluation, canonical source, context ────────────
# ──          compressor, prompt cache, pluggable runtimes, ───────────
# ──          context engine, capability backend,            ───────────
# ──          evaluation engine, health check, request       ───────────
# ──          validation                                     ───────────
from loom_ai.contracts_phase9 import (
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
    # Phase 1 -- 7
    "ChunkingStrategy",
    "ConversationManager",
    "ExecutionPattern",
    "KnowledgePipeline",
    "ModelRouter",
    "PersistentMemoryBackend",
    "StructuredOutputMixin",
    # Phase 2 -- 8
    "BudgetTracker",
    "LearningExtractor",
    "ObservabilityBackend",
    "ResiliencePolicy",
    "StrategySelector",
    "TranscriptStore",
    "WorkflowEngine",
    "WorkflowStorageBackend",
    # Phase 3 -- 6
    "CachePolicy",
    "EvaluationHarness",
    "FeedbackLoopDetector",
    "HumanInTheLoop",
    "SessionInitializer",
    "WorkerRegistry",
    # Phase 4 -- 5
    "BeliefManager",
    "ExternalGraphAdapter",
    "GraphRetriever",
    "KnowledgeGraph",
    "TemporalKnowledgeStore",
    # Phase 5 -- 8
    "AgentLifecycleRuntime",
    "AgentMemory",
    "EvalSuite",
    "GenAITelemetry",
    "InferenceRouter",
    "OutputValidator",
    "ProgramOptimizer",
    "SecurityGate",
    # Phase 6 -- 7
    "ACPAdapter",
    "AgentCapabilityRegistry",
    "AgentEnvironment",
    "AgentLoop",
    "ContextAssembler",
    "RecipeExecutor",
    "TrajectoryStore",
    # Phase 7 -- 4
    "CatalogSynchronizer",
    "PolicyRegistry",
    "ProviderCapabilityRegistry",
    "ProviderRegistry",
    # Phase 8 -- 9
    "CapabilitySelector",
    "ConsensusStrategy",
    "EvalCapabilityRegistry",
    "EvaluationEnvironment",
    "InferenceOptimizer",
    "InteractionEvaluator",
    "OutputNormalizer",
    "SkillEstimator",
    "TournamentRunner",
    # Phase 9 -- 10
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
]
