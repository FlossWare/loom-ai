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

- **Domain modules are implementation artifacts.** The files
  `contracts_core.py` through `contracts_context.py`, `contracts_api.py`,
  and `protocols.py` may be reorganized, merged, or renamed in future
  releases. They are not an API commitment.
- **The `loom_ai.contracts` facade is the stable import path.** Import
  from it to avoid breakage when internal modules change.
- **Old import paths still work.** Existing code that imports from
  `loom_ai.protocols` or individual domain modules will continue to work.
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
| `SecretsBackend` | `protocols` | Async secret/API-key storage | stable | `EnvSecretsBackend`, `PostgresqlSecretsBackend`, `RotatingSecretsBackend` |
| `EmbeddingBackend` | `protocols` | Provider-agnostic vector-embedding generation | stable | `NoopEmbeddingBackend`, `OpenAIEmbeddingBackend`, `LiteLLMEmbeddingBackend` |
| `SearchBackend` | `protocols` | Full-text, semantic, and hybrid search | stable | `MemorySearchBackend`, `PostgresqlSearchBackend` |
| `LLMBackend` | `protocols` | Provider-agnostic chat completion interface | stable | `HttpLLMBackend` |
| `ModelSelectionStrategy` | `protocols` | Pluggable model selection strategy for routing | stable | `ThompsonSamplingSelector` |
| `ToolProvider` | `protocols` | MCP-shaped tool listing and invocation | stable | `MemoryToolProvider` |
| `ResourceProvider` | `protocols` | MCP-shaped resource listing and reading | stable | `MemoryResourceProvider` |
| `TaskRunner` | `protocols` | Strategy for executing a single task | stable | `LLMTaskRunner`, `NoopTaskRunner` |

> **Deprecation note:** `GraphBackend` in `protocols.py` is a deprecated alias
> for `KnowledgeGraph` (defined in `contracts_graph.py`). New code should use
> `KnowledgeGraph` directly. The alias remains for backward compatibility.

## Orchestration (7 protocols)

Structured output, conversation management, persistent memory, model
routing, execution patterns, RAG ingestion, and knowledge pipelines.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `StructuredOutputMixin` | `contracts_core` | Schema-validated LLM output with retries | stable | `StructuredOutputBackend` |
| `ConversationManager` | `contracts_core` | Multi-turn session management | stable | `InMemoryConversationManager` |
| `PersistentMemoryBackend` | `contracts_core` | Named memory storage and recall across sessions | stable | `InMemoryPersistentMemory`, `PostgresqlPersistentMemory` |
| `ModelRouter` | `contracts_core` | Provider-aware routing with fallback and cost | extracted | Now in [model-router-ai](https://github.com/FlossWare/model-router-ai) |
| `ExecutionPattern` | `contracts_core` | Pluggable multi-model execution strategies | stable | `ConsensusPattern`, `CascadePattern`, `MapReducePattern` |
| `ChunkingStrategy` | `contracts_core` | Synchronous text-chunking for RAG ingestion | stable | `TokenChunker` |
| `KnowledgePipeline` | `contracts_core` | End-to-end RAG ingestion and retrieval | stable | `InMemoryKnowledgePipeline`, `PostgresqlKnowledgeStore` |

## Infrastructure (8 protocols)

Workflow execution, learning/feedback, strategy selection, budget
tracking, transcript storage, resilience, and observability.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `WorkflowEngine` | `contracts_workflow` | Execute, resume, and inspect multi-phase workflows | stable | `SimpleWorkflowEngine` |
| `WorkflowStorageBackend` | `contracts_workflow` | Persistence for workflow executions and worker results | stable | `InMemoryWorkflowStorage` |
| `LearningExtractor` | `contracts_workflow` | Detect feedback, record experiences, extract learnings | stable | `SimpleLearningExtractor` |
| `StrategySelector` | `contracts_workflow` | Thompson-Sampling strategy selection | stable | `ThompsonSamplingSelector` |
| `BudgetTracker` | `contracts_workflow` | Track token usage and cost against budgets | stable | `InMemoryBudgetTracker`, `CostTracker` |
| `TranscriptStore` | `contracts_workflow` | Persist and search conversation transcripts | stable | `InMemoryTranscriptStore` |
| `ResiliencePolicy` | `contracts_workflow` | Circuit-breaker and rate-limiting for LLM providers | stable | `CircuitBreakerPolicy`, `ResilientProvider` |
| `ObservabilityBackend` | `contracts_workflow` | Metrics, structured logging, and distributed tracing | stable | `InMemoryObservability`, `PrometheusExporter`, `ExecutionTelemetry` |

## Session and Control (6 protocols)

Session bootstrapping, worker fleet management, prompt caching,
evaluation, feedback loop detection, and human-in-the-loop.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `SessionInitializer` | `contracts_session` | Bootstrap orchestration session with fleet context | stable | `SimpleSessionInitializer` |
| `WorkerRegistry` | `contracts_session` | Registry for managing fleet worker nodes | stable | `InMemoryWorkerRegistry` |
| `CachePolicy` | `contracts_session` | Prompt-caching strategy for provider-specific hints | stable | `PromptCachePolicy` |
| `EvaluationHarness` | `contracts_session` | Multi-model adversarial evaluation of outputs | stable | `SimpleEvaluationHarness` |
| `FeedbackLoopDetector` | `contracts_session` | Detect self-referential feedback loops in the fleet | stable | `SimpleFeedbackLoopDetector` |
| `HumanInTheLoop` | `contracts_session` | Request human input during orchestration | stable | `AutoApproveHumanInTheLoop`, `CallbackHumanInTheLoop` |

## Knowledge Graph (5 protocols)

Knowledge graph operations, temporal validity, GraphRAG retrieval,
external graph ingestion, and belief/evidence management.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `KnowledgeGraph` | `contracts_graph` | Core entity, relationship, and claim operations | experimental | `InMemoryKnowledgeGraph` |
| `TemporalKnowledgeStore` | `contracts_graph` | Temporal validity and historical queries | experimental | `InMemoryTemporalKnowledgeStore` |
| `GraphRetriever` | `contracts_graph` | Graph-enhanced retrieval (local/global/hybrid) | experimental | `InMemoryGraphRetriever` |
| `ExternalGraphAdapter` | `contracts_graph` | External graph and code graph ingestion | experimental | `InMemoryExternalGraphAdapter` |
| `BeliefManager` | `contracts_graph` | Belief, evidence, contradiction, and consensus | experimental | `InMemoryBeliefManager` |

## Advanced Evaluation and Telemetry (8 protocols)

Dataset-driven evaluation, GenAI-specific observability, inference
routing, agent lifecycle, agent memory, output validation, security,
and program optimization.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `EvalSuite` | `contracts_inference` | Dataset-driven evaluation and regression testing | experimental | `InMemoryEvalSuite` |
| `GenAITelemetry` | `contracts_inference` | GenAI-specific observability with semantic spans | experimental | `InMemoryGenAITelemetry` |
| `InferenceRouter` | `contracts_inference` | Capability-aware model routing with adaptive selection | experimental | `InMemoryInferenceRouter` |
| `AgentLifecycleRuntime` | `contracts_inference` | Agent lifecycle, state, and durable execution | experimental | `InMemoryAgentLifecycleRuntime` |
| `AgentMemory` | `contracts_inference` | Persistent, scoped, typed agent memory | experimental | `InMemoryAgentMemory` |
| `OutputValidator` | `contracts_inference` | Schema-driven output validation and tool auth | experimental | `InMemoryOutputValidator` |
| `SecurityGate` | `contracts_inference` | AI security, authorization, and trust boundaries | experimental | `InMemorySecurityGate` |
| `ProgramOptimizer` | `contracts_inference` | Evaluation-driven prompt/model/strategy optimization | experimental | `InMemoryProgramOptimizer` |

## Agent Architecture (7 protocols)

Agent loop, recipe execution, ACP interoperability, context assembly,
trajectory capture, executable environments, and capability taxonomy.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `AgentLoop` | `contracts_agent` | Re-entrant agent loop with pause/resume/cancel | experimental | `InMemoryAgentLoop` |
| `RecipeExecutor` | `contracts_agent` | Portable, declarative agent recipe execution | experimental | `InMemoryRecipeExecutor` |
| `ACPAdapter` | `contracts_agent` | ACP agent interoperability and session management | experimental | `InMemoryACPAdapter` |
| `ContextAssembler` | `contracts_agent` | Context construction, budgeting, and compaction | experimental | `InMemoryContextAssembler` |
| `TrajectoryStore` | `contracts_agent` | Trajectory capture, replay, and curation | experimental | `InMemoryTrajectoryStore` |
| `AgentEnvironment` | `contracts_agent` | Executable environment lifecycle and observation | experimental | `InMemoryAgentEnvironment` |
| `AgentCapabilityRegistry` | `contracts_agent` | Agent/model capability taxonomy and matching | experimental | `InMemoryAgentCapabilityRegistry` |

## Provider Discovery (4 protocols)

Provider and model registry, capability/quota metadata, policy
enforcement, and catalog synchronization.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `ProviderRegistry` | `contracts_provider` | Dynamic provider and model discovery | experimental | `InMemoryProviderRegistry` |
| `ProviderCapabilityRegistry` | `contracts_provider` | Rate limits, quotas, pricing metadata | experimental | `InMemoryProviderCapabilityRegistry` |
| `PolicyRegistry` | `contracts_provider` | Provider policy, privacy, and eligibility | experimental | `InMemoryPolicyRegistry` |
| `CatalogSynchronizer` | `contracts_provider` | Model catalog sync and staleness detection | experimental | `InMemoryCatalogSynchronizer` |

## Competitive Evaluation (9 protocols)

Capability registry, capability selection, interaction evaluation,
Bayesian skill estimation, evaluation environments, tournaments,
inference optimization, output normalization, and consensus strategies.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `EvalCapabilityRegistry` | `contracts_capability` | Capability registry and discovery for evaluation | experimental | `InMemoryEvalCapabilityRegistry` |
| `CapabilitySelector` | `contracts_capability` | Capability health, fallback, and backend selection | experimental | `InMemoryCapabilitySelector` |
| `InteractionEvaluator` | `contracts_capability` | Multi-agent interaction evaluation | experimental | `InMemoryInteractionEvaluator` |
| `SkillEstimator` | `contracts_capability` | Bayesian agent capability and skill estimation | experimental | `InMemorySkillEstimator` |
| `EvaluationEnvironment` | `contracts_capability` | Dynamic multi-agent evaluation environment | experimental | `InMemoryEvaluationEnvironment` |
| `TournamentRunner` | `contracts_capability` | Multi-model competitive evaluation | experimental | `InMemoryTournamentRunner` |
| `InferenceOptimizer` | `contracts_capability` | Adaptive inference parameter optimization | experimental | `InMemoryInferenceOptimizer` |
| `OutputNormalizer` | `contracts_capability` | Model output normalization and semantic comparison | experimental | `InMemoryOutputNormalizer` |
| `ConsensusStrategy` | `contracts_capability` | Pluggable consensus/ensemble/voting strategies | experimental | `InMemoryConsensusStrategy` |

## Pluggable Runtimes (10 protocols)

Model evaluation, canonical source management, context compression,
prompt cache optimization, pluggable agent runtimes, context engines,
capability backends, evaluation engines, health checks, and request
validation.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `ModelEvaluationCandidate` | `contracts_context` | Provider-neutral model evaluation and profiling | experimental | `InMemoryModelEvaluationCandidate` |
| `CanonicalSourceIndex` | `contracts_context` | Canonical-source vs derived-index lifecycle | experimental | `InMemoryCanonicalSourceIndex` |
| `ContextCompressor` | `contracts_context` | Reversible, content-aware context compression | experimental | `InMemoryContextCompressor` |
| `PromptCacheOptimizer` | `contracts_context` | Provider-neutral prompt-cache optimization | experimental | `InMemoryPromptCacheOptimizer` |
| `PluggableAgentRuntime` | `contracts_context` | Interchangeable agent runtimes (Goose, Claude Code, etc.) | experimental | `InMemoryPluggableAgentRuntime` |
| `ContextEngine` | `contracts_context` | Pluggable context-engineering middleware | experimental | `InMemoryContextEngine` |
| `CapabilityBackend` | `contracts_context` | Pluggable capability and tool backend | experimental | `InMemoryCapabilityBackend` |
| `EvaluationEngine` | `contracts_context` | Provider-neutral evaluation and tournament engine | experimental | `InMemoryEvaluationEngine` |
| `HealthCheckPolicy` | `contracts_context` | Authenticated health-check semantics | experimental | `InMemoryHealthCheckPolicy` |
| `RequestValidator` | `contracts_context` | REST API request/response validation | experimental | `InMemoryRequestValidator` |

## API (3 protocols)

REST API request lifecycle, error handling, and middleware.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `RequestLifecycle` | `contracts_api` | Validate, authorize, execute, respond lifecycle | stable | `InMemoryRequestLifecycle` |
| `ErrorHandler` | `contracts_api` | Centralized error handling and formatting | stable | `InMemoryErrorHandler` |
| `Middleware` | `contracts_api` | Pre/post request hooks | stable | `PassthroughMiddleware` |

## Execution (3 protocols)

Execution steps, pipelines, and observers for sequential step execution
with lifecycle hooks.

| Protocol | Source | Purpose | Stability | Backends |
|----------|--------|---------|-----------|----------|
| `ExecutionStep` | `contracts_execution` | Single unit of work in an execution pipeline | stable | `NoopExecutionStep` |
| `ExecutionPipeline` | `contracts_execution` | Sequential step runner with cancellation and deadlines | stable | `SequentialExecutionPipeline` |
| `ExecutionObserver` | `contracts_execution` | Lifecycle observer for pipeline step events | stable | `LoggingExecutionObserver` |

---

## Summary by stability

| Stability | Count |
|-----------|-------|
| stable | 38 |
| experimental | 43 |
| **Total** | **81** |
