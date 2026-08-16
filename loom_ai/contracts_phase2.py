"""Phase 2 protocol definitions for loom-ai backends.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All methods are
async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models import ChatMessage
    from loom_ai.models_phase2 import (
        BudgetStatus,
        CircuitState,
        CostReport,
        FeedbackSignal,
        Learning,
        StrategyStats,
        TokenUsage,
        TranscriptSummary,
        WorkerResult,
        WorkflowDefinition,
        WorkflowExecution,
        WorkflowResult,
        WorkflowStatus,
    )


# -- Workflow (#96) ----------------------------------------------------------


@runtime_checkable
class WorkflowEngine(Protocol):
    """Execute, resume, and inspect multi-phase workflows."""

    async def execute(
        self, workflow: WorkflowDefinition, *, args: dict | None = None
    ) -> WorkflowResult:
        """Run *workflow* to completion and return the result."""
        ...

    async def resume(self, run_id: str) -> WorkflowResult:
        """Resume an interrupted workflow run."""
        ...

    async def status(self, run_id: str) -> WorkflowStatus:
        """Return the current status of a running workflow."""
        ...


@runtime_checkable
class WorkflowStorageBackend(Protocol):
    """Persistence layer for workflow executions and worker results."""

    async def store_execution(self, execution: WorkflowExecution) -> str:
        """Persist an execution record and return its id."""
        ...

    async def store_worker_result(self, exec_id: str, result: WorkerResult) -> None:
        """Attach a worker result to the given execution."""
        ...

    async def find_similar(
        self, task_description: str, *, limit: int = 10
    ) -> list[WorkflowExecution]:
        """Return executions whose task description is similar to *task_description*."""
        ...

    async def get_execution(self, exec_id: str) -> WorkflowExecution | None:
        """Return an execution by id, or ``None`` if not found."""
        ...


# -- Learning (#97) ----------------------------------------------------------


@runtime_checkable
class LearningExtractor(Protocol):
    """Detect feedback, record experiences, and extract learnings."""

    async def detect_feedback(
        self, messages: list[ChatMessage]
    ) -> list[FeedbackSignal]:
        """Scan *messages* for implicit or explicit feedback signals."""
        ...

    async def record_experience(
        self,
        task: str,
        outcome: str,
        *,
        context: dict | None = None,
    ) -> str:
        """Persist a task/outcome experience and return its id."""
        ...

    async def extract_learnings(self, experience_id: str) -> list[Learning]:
        """Derive actionable learnings from a stored experience."""
        ...

    async def update_strategy(
        self, strategy: str, outcome: str, *, reward: float
    ) -> None:
        """Update strategy bandit state with an observed reward."""
        ...


# -- Strategy (#98) ----------------------------------------------------------


@runtime_checkable
class StrategySelector(Protocol):
    """Thompson-Sampling strategy selection for task routing."""

    async def select(self, task_type: str, *, candidates: list[str]) -> str:
        """Choose the best strategy for *task_type* from *candidates*."""
        ...

    async def update(self, strategy: str, task_type: str, *, reward: float) -> None:
        """Record a reward observation for a strategy/task-type pair."""
        ...

    async def performance(
        self, *, task_type: str | None = None
    ) -> dict[str, StrategyStats]:
        """Return performance statistics, optionally filtered by task type."""
        ...


# -- Budget (#99) ------------------------------------------------------------


@runtime_checkable
class BudgetTracker(Protocol):
    """Track token usage and cost against configurable budgets."""

    async def record_usage(
        self, model: str, usage: TokenUsage, *, task_id: str | None = None
    ) -> None:
        """Record token consumption for a model invocation."""
        ...

    async def remaining(self) -> BudgetStatus:
        """Return the current budget status."""
        ...

    async def set_budget(
        self,
        *,
        max_tokens: int | None = None,
        max_cost: float | None = None,
    ) -> None:
        """Set or update budget limits."""
        ...

    async def cost_report(self) -> CostReport:
        """Return an aggregated cost breakdown."""
        ...


# -- Transcript (#100) -------------------------------------------------------


@runtime_checkable
class TranscriptStore(Protocol):
    """Persist and search conversation transcripts."""

    async def store(
        self,
        session_id: str,
        messages: list[ChatMessage],
        *,
        metadata: dict | None = None,
    ) -> None:
        """Store messages for a session."""
        ...

    async def load(self, session_id: str) -> list[ChatMessage]:
        """Load all messages for a session."""
        ...

    async def search(self, query: str, *, limit: int = 10) -> list[TranscriptSummary]:
        """Search transcripts by content and return summaries."""
        ...

    async def list_sessions(self, *, limit: int = 20) -> list[TranscriptSummary]:
        """Return recent transcript session summaries."""
        ...


# -- Resilience (#101) -------------------------------------------------------


@runtime_checkable
class ResiliencePolicy(Protocol):
    """Circuit-breaker and rate-limiting policy for LLM providers."""

    async def should_allow(self, provider: str) -> bool:
        """Return whether requests to *provider* are currently allowed."""
        ...

    async def record_outcome(
        self, provider: str, *, success: bool, latency_ms: float
    ) -> None:
        """Record the outcome of a request to *provider*."""
        ...

    async def circuit_state(self, provider: str) -> CircuitState:
        """Return the circuit-breaker state for *provider*."""
        ...


# -- Observability (#102) ----------------------------------------------------


@runtime_checkable
class ObservabilityBackend(Protocol):
    """Metrics, structured logging, and distributed tracing."""

    async def record_metric(
        self, name: str, value: float, *, labels: dict | None = None
    ) -> None:
        """Record a numeric metric data point."""
        ...

    async def log_event(
        self,
        event: str,
        *,
        level: str = "info",
        context: dict | None = None,
    ) -> None:
        """Emit a structured log event."""
        ...

    async def start_span(self, name: str, *, parent: str | None = None) -> str:
        """Begin a tracing span and return its span id."""
        ...

    async def end_span(self, span_id: str, *, status: str = "ok") -> None:
        """Close a tracing span."""
        ...
