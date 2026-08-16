"""Phase 2 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 2 protocols reference these types for their method
signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Workflow models ---------------------------------------------------------


@dataclass
class WorkflowDefinition:
    """Declarative description of a multi-phase workflow."""

    id: str
    name: str
    description: str
    phases: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Outcome produced by a completed (or failed) workflow run."""

    workflow_id: str
    run_id: str
    status: str
    phases_completed: list[str] = field(default_factory=list)
    outputs: dict = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class WorkflowStatus:
    """Live progress snapshot for a running workflow."""

    run_id: str
    phase: str
    progress: float
    started_at: str = ""


@dataclass
class WorkflowExecution:
    """Persisted record of a single workflow execution."""

    id: str
    workflow_name: str
    task_description: str
    total_workers: int
    total_duration_ms: float
    outcome: str
    created_at: str = ""


@dataclass
class WorkerResult:
    """Individual worker output within a workflow execution."""

    id: str
    execution_id: str
    model: str
    content: str
    latency_ms: float
    tokens_used: int
    success: bool


# -- Learning models ---------------------------------------------------------


@dataclass
class FeedbackSignal:
    """A detected feedback signal extracted from conversation messages."""

    type: str
    content: str
    confidence: float
    source_message: str


@dataclass
class Learning:
    """A single actionable insight extracted from an experience."""

    id: str
    content: str
    category: str
    source_experience: str
    created_at: str = ""


# -- Strategy models ---------------------------------------------------------


@dataclass
class StrategyStats:
    """Thompson-Sampling bandit state for a strategy/task-type pair."""

    strategy: str
    task_type: str
    total_trials: int
    successes: int
    avg_reward: float
    alpha: float
    beta: float


# -- Budget & cost models ----------------------------------------------------


@dataclass
class TokenUsage:
    """Token counts for a single LLM invocation."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class BudgetStatus:
    """Current budget consumption and remaining allowance."""

    tokens_used: int
    tokens_remaining: int | None
    cost_used: float
    cost_remaining: float | None


@dataclass
class CostReport:
    """Aggregated cost breakdown across models, providers, and tasks."""

    total_cost: float
    by_model: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)
    by_task: dict = field(default_factory=dict)


# -- Transcript models -------------------------------------------------------


@dataclass
class TranscriptSummary:
    """Lightweight summary of a stored transcript session."""

    session_id: str
    created_at: str
    message_count: int
    preview: str
    metadata: dict = field(default_factory=dict)


# -- Resilience models -------------------------------------------------------


@dataclass
class CircuitState:
    """Circuit-breaker state for a provider endpoint."""

    state: str  # "closed", "open", or "half_open"
    failure_count: int
    last_failure_at: str = ""
    next_retry_at: str = ""
