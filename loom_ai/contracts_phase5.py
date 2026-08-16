"""Phase 5 protocol definitions for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All I/O methods
are async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 5 covers eight core contract areas:

- **EvalSuite** -- dataset-driven evaluation and regression testing (#51)
- **GenAITelemetry** -- GenAI-specific observability and telemetry (#52)
- **InferenceRouter** -- model provider, inference, and adaptive routing (#53)
- **AgentLifecycleRuntime** -- agent lifecycle, state, and durable execution (#54)
- **AgentMemory** -- persistent, scoped, typed agent memory (#55)
- **OutputValidator** -- schema-driven output validation and tool auth (#56)
- **SecurityGate** -- AI security, authorization, and trust boundaries (#57)
- **ProgramOptimizer** -- evaluation-driven program optimization (#58)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_phase5 import (
        AgentEvent,
        AgentLifecycleState,
        AgentMemoryEntry,
        CapabilityPolicy,
        Checkpoint,
        ContentScanResult,
        EvalDataset,
        EvalRunResult,
        ExperimentRun,
        GenAISpanAttributes,
        Handoff,
        InferenceEndpoint,
        MemoryQuery,
        MemoryScope,
        ModelCapabilities,
        OptimizationResult,
        OptimizationTarget,
        RedactionPolicy,
        RegressionComparison,
        RoutingDecision,
        SchemaDefinition,
        SecurityEvent,
        TelemetrySummary,
        ToolExecutionResult,
        ToolIntent,
        ValidationResult,
    )


# -- AI Evaluation & Regression Testing (#51) --------------------------------


@runtime_checkable
class EvalSuite(Protocol):
    """Dataset-driven evaluation, metric computation, and regression testing.

    Complements :class:`~loom_ai.contracts_phase3.EvaluationHarness` which
    provides multi-model adversarial evaluation of individual outputs.
    ``EvalSuite`` operates at the *dataset* level -- running batches of
    evaluation cases, computing named metrics, and comparing runs to
    detect regressions across model or configuration changes.
    """

    async def run(
        self,
        dataset: EvalDataset,
        *,
        model: str | None = None,
        evaluators: list[str] | None = None,
        config: dict | None = None,
    ) -> EvalRunResult:
        """Execute evaluation cases and return aggregated metric scores."""
        ...

    async def compare(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
    ) -> RegressionComparison:
        """Compare two runs and identify regressions and improvements."""
        ...

    async def get_run(self, run_id: str) -> EvalRunResult | None:
        """Retrieve a stored evaluation run by id."""
        ...

    async def list_datasets(self) -> list[EvalDataset]:
        """Return available evaluation datasets."""
        ...


# -- GenAI Observability & Telemetry (#52) -----------------------------------


@runtime_checkable
class GenAITelemetry(Protocol):
    """GenAI-specific observability with semantic span attributes.

    Complements :class:`~loom_ai.contracts_phase2.ObservabilityBackend`
    which provides general-purpose metrics, logging, and tracing.
    ``GenAITelemetry`` adds AI-operation-specific semantics: model/provider
    attribution, token and cost tracking per span, retrieval and tool-call
    tracing, and privacy-aware redaction -- aligned with OpenTelemetry
    GenAI semantic conventions.
    """

    async def record_span(
        self,
        span_id: str,
        attributes: GenAISpanAttributes,
    ) -> None:
        """Attach GenAI semantic attributes to an existing trace span."""
        ...

    async def set_redaction_policy(self, policy: RedactionPolicy) -> None:
        """Configure the active redaction policy for telemetry output."""
        ...

    async def summarize(
        self,
        *,
        window_minutes: int = 60,
    ) -> TelemetrySummary:
        """Return aggregated telemetry for the given time window."""
        ...

    async def export_spans(
        self,
        *,
        limit: int = 100,
        operation: str | None = None,
    ) -> list[dict]:
        """Export recent spans as plain dicts for external consumption."""
        ...


# -- Model Provider, Inference, and Routing (#53) ---------------------------


@runtime_checkable
class InferenceRouter(Protocol):
    """Capability-aware model routing with adaptive selection.

    Complements :class:`~loom_ai.contracts_phase1.ModelRouter` which
    provides provider-level routing, fallback, and cost estimation.
    ``InferenceRouter`` adds inference-backend abstraction, capability-based
    model selection, adaptive routing hooks (e.g. Thompson Sampling), and
    quota/health signalling at the endpoint level.
    """

    async def select(
        self,
        *,
        capabilities: ModelCapabilities | None = None,
        preferred_model: str | None = None,
        budget_usd: float | None = None,
    ) -> InferenceEndpoint:
        """Select an inference endpoint matching the requested capabilities."""
        ...

    async def register_endpoint(self, endpoint: InferenceEndpoint) -> None:
        """Register an inference endpoint with the router."""
        ...

    async def record_outcome(
        self,
        endpoint_id: str,
        *,
        success: bool,
        latency_ms: float,
        tokens_used: int = 0,
    ) -> None:
        """Feed an observed outcome back into the adaptive routing model."""
        ...

    async def get_decision_log(self, *, limit: int = 20) -> list[RoutingDecision]:
        """Return recent routing decisions for auditability."""
        ...

    async def list_endpoints(
        self, *, healthy_only: bool = False
    ) -> list[InferenceEndpoint]:
        """Return registered endpoints, optionally filtered to healthy ones."""
        ...


# -- Agent Runtime, State, and Durable Execution (#54) ----------------------


@runtime_checkable
class AgentLifecycleRuntime(Protocol):
    """Agent lifecycle management with durable execution semantics.

    Complements :class:`~loom_ai.contracts_phase2.WorkflowEngine` which
    handles multi-phase workflow execution and resumption.
    ``AgentLifecycleRuntime`` focuses on individual agent lifecycle -- explicit
    state management, checkpointing, handoffs between agents, tool-call
    lifecycle, retries, interruption, and resumption with durable
    execution guarantees.
    """

    async def start(
        self,
        agent_id: str,
        *,
        initial_state: AgentLifecycleState | None = None,
        config: dict | None = None,
    ) -> str:
        """Start an agent and return its run id."""
        ...

    async def checkpoint(self, run_id: str) -> Checkpoint:
        """Create a durable checkpoint of the current agent state."""
        ...

    async def resume(self, checkpoint_id: str) -> str:
        """Resume an agent from a checkpoint and return the new run id."""
        ...

    async def handoff(
        self,
        run_id: str,
        to_agent: str,
        *,
        reason: str = "",
        context: dict | None = None,
    ) -> Handoff:
        """Transfer control from the current agent to *to_agent*."""
        ...

    async def interrupt(self, run_id: str, *, reason: str = "") -> None:
        """Interrupt a running agent, preserving state for later resumption."""
        ...

    async def get_state(self, run_id: str) -> AgentLifecycleState | None:
        """Return the current state of an agent run."""
        ...

    async def get_events(self, run_id: str, *, limit: int = 50) -> list[AgentEvent]:
        """Return lifecycle events for an agent run."""
        ...


# -- Persistent Agent Memory (#55) ------------------------------------------


@runtime_checkable
class AgentMemory(Protocol):
    """Scoped, typed persistent memory for agents.

    Complements :class:`~loom_ai.contracts_phase1.PersistentMemoryBackend`
    which provides named key-value memory storage and recall.
    ``AgentMemory`` adds agent-specific semantics: typed memory categories
    (semantic, episodic, procedural, working), confidence scores, temporal
    validity, supersession tracking, and agent/user/application scoping.
    """

    async def store(
        self,
        entry: AgentMemoryEntry,
    ) -> str:
        """Store a memory entry and return its id."""
        ...

    async def recall(
        self,
        query: MemoryQuery,
    ) -> list[AgentMemoryEntry]:
        """Retrieve memory entries matching the query."""
        ...

    async def supersede(
        self,
        entry_id: str,
        replacement: AgentMemoryEntry,
    ) -> str:
        """Mark *entry_id* as superseded and store the replacement."""
        ...

    async def forget(
        self,
        entry_id: str,
    ) -> bool:
        """Remove a memory entry.  Return ``True`` if it existed."""
        ...

    async def list_scopes(self) -> list[MemoryScope]:
        """Return available memory scopes."""
        ...

    async def count(
        self,
        *,
        scope: str | None = None,
        memory_type: str | None = None,
    ) -> int:
        """Return the number of entries matching the given filters."""
        ...


# -- Structured Output & Tool (#56) -----------------------------------------


@runtime_checkable
class OutputValidator(Protocol):
    """Schema-driven output validation with repair and tool authorization.

    Complements :class:`~loom_ai.contracts_phase1.StructuredOutputMixin`
    which provides schema-validated chat completion with retries, and
    :class:`~loom_ai.protocols.ToolProvider` which provides tool
    listing and invocation.  ``OutputValidator`` separates validation,
    repair, and failure semantics from the LLM call, and adds a tool
    authorization boundary between model-generated intent and actual
    execution.
    """

    async def validate(
        self,
        output: Any,
        schema: SchemaDefinition,
    ) -> ValidationResult:
        """Validate *output* against *schema*."""
        ...

    async def repair(
        self,
        output: Any,
        schema: SchemaDefinition,
        *,
        max_attempts: int = 3,
    ) -> tuple[Any, ValidationResult]:
        """Attempt to repair *output* to conform to *schema*."""
        ...

    async def authorize_tool(
        self,
        intent: ToolIntent,
        policy: CapabilityPolicy,
    ) -> ToolExecutionResult:
        """Authorize and execute a model-generated tool intent."""
        ...

    async def list_schemas(self) -> list[SchemaDefinition]:
        """Return registered schema definitions."""
        ...


# -- AI Security, Authorization, and Trust Boundary (#57) -------------------


@runtime_checkable
class SecurityGate(Protocol):
    """Security enforcement for AI operations.

    Defines trust boundaries, tool/resource authorization policies,
    prompt-injection scanning, credential isolation, and audit-event
    recording for agents, models, tools, and data stores.
    """

    async def check_policy(
        self,
        agent_id: str,
        action: str,
        *,
        resource: str | None = None,
    ) -> bool:
        """Return whether *agent_id* is allowed to perform *action*."""
        ...

    async def scan_content(
        self,
        content: str,
        *,
        context: str = "",
    ) -> ContentScanResult:
        """Scan *content* for prompt injection or policy violations."""
        ...

    async def set_policy(
        self,
        policy: CapabilityPolicy,
    ) -> None:
        """Register or update an authorization policy."""
        ...

    async def get_policy(
        self,
        agent_id: str,
    ) -> CapabilityPolicy | None:
        """Return the policy for *agent_id*, or ``None`` if none is set."""
        ...

    async def record_event(
        self,
        event: SecurityEvent,
    ) -> None:
        """Record an auditable security event."""
        ...

    async def get_events(
        self,
        *,
        agent_id: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[SecurityEvent]:
        """Return security events, optionally filtered."""
        ...


# -- AI Program Optimization (#58) ------------------------------------------


@runtime_checkable
class ProgramOptimizer(Protocol):
    """Evaluation-driven optimization of prompts, models, and strategies.

    Complements :class:`~loom_ai.contracts_phase2.StrategySelector` which
    provides Thompson-Sampling strategy selection for task routing.
    ``ProgramOptimizer`` generalises optimization to arbitrary targets
    (prompts, retrieval strategies, model selection, workflows), integrates
    with :class:`EvalSuite` for objective measurement, and adds experiment
    tracking and reproducibility semantics.
    """

    async def register_target(
        self,
        target: OptimizationTarget,
    ) -> None:
        """Register a component as eligible for optimization."""
        ...

    async def run_experiment(
        self,
        target_id: str,
        variant: str,
        *,
        eval_dataset_id: str | None = None,
        config: dict | None = None,
    ) -> ExperimentRun:
        """Run a single experiment for *target_id* using *variant*."""
        ...

    async def optimize(
        self,
        target_id: str,
        *,
        max_iterations: int = 10,
        objective: str = "quality",
    ) -> OptimizationResult:
        """Run an optimization loop and return the best result."""
        ...

    async def get_experiments(
        self,
        target_id: str,
        *,
        limit: int = 20,
    ) -> list[ExperimentRun]:
        """Return experiment history for a target."""
        ...
