# Canonical Contract Inventory

loom-ai defines **81 `@runtime_checkable` Protocol contracts** that form
the public API surface for backend implementations. All protocols use
structural subtyping -- implementations do **not** need to import or
inherit from these classes.

## Stable import path

```python
from loom_ai.contracts import StorageBackend, WorkflowEngine, ...
```

The `loom_ai.contracts` facade re-exports every protocol from a single
namespace. This is the **recommended and stable** import path.

## Versioning and compatibility

- **Phase modules are implementation artifacts.** The files
  `contracts_phase1.py` through `contracts_phase9.py`, `contracts_api.py`,
  and `protocols.py` may be reorganized, merged, or renamed in future
  releases. They are not an API commitment.
- **The `loom_ai.contracts` facade is the stable import path.** Import
  from it to avoid breakage when internal modules change.
- **Old import paths still work.** Existing code that imports from
  `loom_ai.protocols` or individual phase modules will continue to work.
  The facade is additive -- it does not change or remove the underlying
  modules.
- **Structural subtyping.** Protocols use `typing.Protocol` with
  `@runtime_checkable`. Any class whose methods match the protocol
  signature satisfies the contract. No explicit inheritance is needed.

---

## Core (11 protocols)

Fundamental storage, queue, secrets, embedding, search, graph, LLM,
tool, resource, and task execution contracts.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `IdempotentStore` | `protocols` | Marker for backends with idempotent write semantics | stable | `MemoryStorageBackend`, `PostgresqlStorageBackend` |
| `StorageBackend` | `protocols` | Async persistence for documents, chunks, and embeddings | stable | `MemoryStorageBackend`, `PostgresqlStorageBackend` |
| `QueueBackend` | `protocols` | Named task queue with enqueue/fetch/complete/requeue | stable | `MemoryQueueBackend`, `RedisQueueBackend` |
| `SecretsBackend` | `protocols` | Async secret/API-key storage | stable | `EnvSecretsBackend`, `PostgresqlSecretsBackend` |
| `EmbeddingBackend` | `protocols` | Provider-agnostic vector-embedding generation | stable | `NoopEmbeddingBackend`, `EmbeddingStore` |
| `SearchBackend` | `protocols` | Full-text, semantic, and hybrid search | stable | `MemorySearchBackend`, `PostgresqlSearchBackend` |
| `GraphBackend` | `protocols` | Knowledge-graph node and edge storage | stable | `MemoryGraphBackend`, `DisabledGraphBackend` |
| `LLMBackend` | `protocols` | Provider-agnostic chat completion interface | stable | `HttpLLMBackend` |
| `ToolProvider` | `protocols` | MCP-shaped tool listing and invocation | stable | `MemoryToolProvider` |
| `ResourceProvider` | `protocols` | MCP-shaped resource listing and reading | stable | `MemoryResourceProvider` |
| `TaskRunner` | `protocols` | Strategy for executing a single task | stable | `LLMTaskRunner`, `NoopTaskRunner` |

## Orchestration (7 protocols)

Structured output, conversation management, persistent memory, model
routing, execution patterns, RAG ingestion, and knowledge pipelines.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `StructuredOutputMixin` | `contracts_phase1` | Schema-validated LLM output with retries | stable | `StructuredOutputBackend` |
| `ConversationManager` | `contracts_phase1` | Multi-turn session management | stable | `InMemoryConversationManager` |
| `PersistentMemoryBackend` | `contracts_phase1` | Named memory storage and recall across sessions | stable | `InMemoryPersistentMemory`, `PostgresqlPersistentMemory` |
| `ModelRouter` | `contracts_phase1` | Provider-aware routing with fallback and cost | stable | `SimpleModelRouter`, `AdaptiveModelRouter` |
| `ExecutionPattern` | `contracts_phase1` | Pluggable multi-model execution strategies | stable | `ConsensusPattern`, `CascadePattern`, `MapReducePattern` |
| `ChunkingStrategy` | `contracts_phase1` | Synchronous text-chunking for RAG ingestion | stable | `TokenChunker` |
| `KnowledgePipeline` | `contracts_phase1` | End-to-end RAG ingestion and retrieval | stable | `InMemoryKnowledgePipeline` |

## Infrastructure (8 protocols)

Workflow execution, learning/feedback, strategy selection, budget
tracking, transcript storage, resilience, and observability.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `WorkflowEngine` | `contracts_phase2` | Execute, resume, and inspect multi-phase workflows | stable | `SimpleWorkflowEngine` |
| `WorkflowStorageBackend` | `contracts_phase2` | Persistence for workflow executions and worker results | stable | `InMemoryWorkflowStorage` |
| `LearningExtractor` | `contracts_phase2` | Detect feedback, record experiences, extract learnings | stable | `SimpleLearningExtractor` |
| `StrategySelector` | `contracts_phase2` | Thompson-Sampling strategy selection | stable | `ThompsonSamplingSelector` |
| `BudgetTracker` | `contracts_phase2` | Track token usage and cost against budgets | stable | `InMemoryBudgetTracker`, `CostTracker` |
| `TranscriptStore` | `contracts_phase2` | Persist and search conversation transcripts | stable | `InMemoryTranscriptStore` |
| `ResiliencePolicy` | `contracts_phase2` | Circuit-breaker and rate-limiting for LLM providers | stable | `CircuitBreakerPolicy`, `ResilientProvider` |
| `ObservabilityBackend` | `contracts_phase2` | Metrics, structured logging, and distributed tracing | stable | `InMemoryObservability`, `PrometheusExporter`, `ExecutionTelemetry` |

## Session and Control (6 protocols)

Session bootstrapping, worker fleet management, prompt caching,
evaluation, feedback loop detection, and human-in-the-loop.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `SessionInitializer` | `contracts_phase3` | Bootstrap orchestration session with fleet context | stable | `SimpleSessionInitializer` |
| `WorkerRegistry` | `contracts_phase3` | Registry for managing fleet worker nodes | stable | `InMemoryWorkerRegistry` |
| `CachePolicy` | `contracts_phase3` | Prompt-caching strategy for provider-specific hints | stable | `PromptCachePolicy` |
| `EvaluationHarness` | `contracts_phase3` | Multi-model adversarial evaluation of outputs | stable | `SimpleEvaluationHarness` |
| `FeedbackLoopDetector` | `contracts_phase3` | Detect self-referential feedback loops in the fleet | stable | `SimpleFeedbackLoopDetector` |
| `HumanInTheLoop` | `contracts_phase3` | Request human input during orchestration | stable | `AutoApproveHumanInTheLoop`, `CallbackHumanInTheLoop` |

## Knowledge Graph (5 protocols)

Knowledge graph operations, temporal validity, GraphRAG retrieval,
external graph ingestion, and belief/evidence management.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `KnowledgeGraph` | `contracts_phase4` | Core entity, relationship, and claim operations | experimental | `InMemoryKnowledgeGraph` |
| `TemporalKnowledgeStore` | `contracts_phase4` | Temporal validity and historical queries | experimental | -- |
| `GraphRetriever` | `contracts_phase4` | Graph-enhanced retrieval (local/global/hybrid) | experimental | -- |
| `ExternalGraphAdapter` | `contracts_phase4` | External graph and code graph ingestion | experimental | -- |
| `BeliefManager` | `contracts_phase4` | Belief, evidence, contradiction, and consensus | experimental | -- |

## Advanced Evaluation and Telemetry (8 protocols)

Dataset-driven evaluation, GenAI-specific observability, inference
routing, agent lifecycle, agent memory, output validation, security,
and program optimization.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `EvalSuite` | `contracts_phase5` | Dataset-driven evaluation and regression testing | experimental | -- |
| `GenAITelemetry` | `contracts_phase5` | GenAI-specific observability with semantic spans | experimental | -- |
| `InferenceRouter` | `contracts_phase5` | Capability-aware model routing with adaptive selection | experimental | -- |
| `AgentLifecycleRuntime` | `contracts_phase5` | Agent lifecycle, state, and durable execution | experimental | -- |
| `AgentMemory` | `contracts_phase5` | Persistent, scoped, typed agent memory | experimental | -- |
| `OutputValidator` | `contracts_phase5` | Schema-driven output validation and tool auth | experimental | -- |
| `SecurityGate` | `contracts_phase5` | AI security, authorization, and trust boundaries | experimental | -- |
| `ProgramOptimizer` | `contracts_phase5` | Evaluation-driven prompt/model/strategy optimization | experimental | -- |

## Agent Architecture (7 protocols)

Agent loop, recipe execution, ACP interoperability, context assembly,
trajectory capture, executable environments, and capability taxonomy.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `AgentLoop` | `contracts_phase6` | Re-entrant agent loop with pause/resume/cancel | experimental | -- |
| `RecipeExecutor` | `contracts_phase6` | Portable, declarative agent recipe execution | experimental | -- |
| `ACPAdapter` | `contracts_phase6` | ACP agent interoperability and session management | experimental | -- |
| `ContextAssembler` | `contracts_phase6` | Context construction, budgeting, and compaction | experimental | -- |
| `TrajectoryStore` | `contracts_phase6` | Trajectory capture, replay, and curation | experimental | -- |
| `AgentEnvironment` | `contracts_phase6` | Executable environment lifecycle and observation | experimental | -- |
| `AgentCapabilityRegistry` | `contracts_phase6` | Agent/model capability taxonomy and matching | experimental | -- |

## Provider Discovery (4 protocols)

Provider and model registry, capability/quota metadata, policy
enforcement, and catalog synchronization.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `ProviderRegistry` | `contracts_phase7` | Dynamic provider and model discovery | experimental | -- |
| `ProviderCapabilityRegistry` | `contracts_phase7` | Rate limits, quotas, pricing metadata | experimental | -- |
| `PolicyRegistry` | `contracts_phase7` | Provider policy, privacy, and eligibility | experimental | -- |
| `CatalogSynchronizer` | `contracts_phase7` | Model catalog sync and staleness detection | experimental | -- |

## Competitive Evaluation (9 protocols)

Capability registry, capability selection, interaction evaluation,
Bayesian skill estimation, evaluation environments, tournaments,
inference optimization, output normalization, and consensus strategies.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `EvalCapabilityRegistry` | `contracts_phase8` | Capability registry and discovery for evaluation | experimental | -- |
| `CapabilitySelector` | `contracts_phase8` | Capability health, fallback, and backend selection | experimental | -- |
| `InteractionEvaluator` | `contracts_phase8` | Multi-agent interaction evaluation | experimental | -- |
| `SkillEstimator` | `contracts_phase8` | Bayesian agent capability and skill estimation | experimental | -- |
| `EvaluationEnvironment` | `contracts_phase8` | Dynamic multi-agent evaluation environment | experimental | -- |
| `TournamentRunner` | `contracts_phase8` | Multi-model competitive evaluation | experimental | -- |
| `InferenceOptimizer` | `contracts_phase8` | Adaptive inference parameter optimization | experimental | -- |
| `OutputNormalizer` | `contracts_phase8` | Model output normalization and semantic comparison | experimental | -- |
| `ConsensusStrategy` | `contracts_phase8` | Pluggable consensus/ensemble/voting strategies | experimental | -- |

## Pluggable Runtimes (10 protocols)

Model evaluation, canonical source management, context compression,
prompt cache optimization, pluggable agent runtimes, context engines,
capability backends, evaluation engines, health checks, and request
validation.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `ModelEvaluationCandidate` | `contracts_phase9` | Provider-neutral model evaluation and profiling | experimental | -- |
| `CanonicalSourceIndex` | `contracts_phase9` | Canonical-source vs derived-index lifecycle | experimental | -- |
| `ContextCompressor` | `contracts_phase9` | Reversible, content-aware context compression | experimental | -- |
| `PromptCacheOptimizer` | `contracts_phase9` | Provider-neutral prompt-cache optimization | experimental | -- |
| `PluggableAgentRuntime` | `contracts_phase9` | Interchangeable agent runtimes (Goose, Claude Code, etc.) | experimental | -- |
| `ContextEngine` | `contracts_phase9` | Pluggable context-engineering middleware | experimental | -- |
| `CapabilityBackend` | `contracts_phase9` | Pluggable capability and tool backend | experimental | -- |
| `EvaluationEngine` | `contracts_phase9` | Provider-neutral evaluation and tournament engine | experimental | -- |
| `HealthCheckPolicy` | `contracts_phase9` | Authenticated health-check semantics | experimental | -- |
| `RequestValidator` | `contracts_phase9` | REST API request/response validation | experimental | -- |

## API (3 protocols)

REST API request lifecycle, error handling, and middleware.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `RequestLifecycle` | `contracts_api` | Validate, authorize, execute, respond lifecycle | stable | -- |
| `ErrorHandler` | `contracts_api` | Centralized error handling and formatting | stable | -- |
| `Middleware` | `contracts_api` | Pre/post request hooks | stable | -- |

## Execution (3 protocols)

Execution steps, pipelines, and observers for sequential step execution
with lifecycle hooks.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `ExecutionStep` | `contracts_execution` | Single unit of work in an execution pipeline | stable | -- |
| `ExecutionPipeline` | `contracts_execution` | Sequential step runner with cancellation and deadlines | stable | `SequentialExecutionPipeline` |
| `ExecutionObserver` | `contracts_execution` | Lifecycle observer for pipeline step events | stable | -- |

---

## Summary by stability

| Stability | Count |
|-----------|-------|
| stable | 38 |
| experimental | 43 |
| **Total** | **81** |
