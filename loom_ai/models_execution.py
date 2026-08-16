"""Execution layer data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  These models support the execution protocol contracts defined
in ``contracts_execution.py``.

The execution layer represents the lifecycle of multi-step pipelines:

- **StepStatus** -- enumeration of possible step outcomes
- **ExecutionStatus** -- enumeration of overall execution outcomes
- **ExecutionContext** -- inputs, deadline, cancellation flag, metadata
- **StepResult** -- per-step outcome with timing and error details
- **ExecutionResult** -- aggregate outcome for a complete pipeline run
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class StepStatus(enum.Enum):
    """Outcome status for a single execution step."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ExecutionStatus(enum.Enum):
    """Aggregate outcome for an entire execution pipeline run."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionContext:
    """Mutable context threaded through an execution pipeline.

    Parameters
    ----------
    execution_id:
        Unique identifier for this execution run.
    inputs:
        Arbitrary input data available to every step.
    deadline:
        ISO-8601 timestamp after which execution should be abandoned.
        Empty string means no deadline.
    metadata:
        Free-form metadata carried through the pipeline.
    cancelled:
        When set to ``True``, the pipeline should stop after the
        current step completes.
    """

    execution_id: str
    inputs: dict = field(default_factory=dict)
    deadline: str = ""
    metadata: dict = field(default_factory=dict)
    cancelled: bool = False


@dataclass
class StepResult:
    """Outcome of a single execution step.

    Parameters
    ----------
    step_id:
        Identifier of the step that produced this result.
    status:
        Whether the step succeeded, failed, was skipped, or cancelled.
    output:
        Arbitrary output data produced by the step.
    duration_ms:
        Wall-clock time in milliseconds the step took to execute.
    error:
        Human-readable error message when ``status`` is ``FAILED``.
    """

    step_id: str
    status: StepStatus
    output: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class ExecutionResult:
    """Aggregate result for an entire execution pipeline run.

    Parameters
    ----------
    execution_id:
        Identifier matching the originating ``ExecutionContext``.
    steps:
        Ordered list of per-step results.
    status:
        Overall outcome derived from individual step statuses.
    total_duration_ms:
        Wall-clock time in milliseconds for the full pipeline run.
    metadata:
        Free-form metadata (e.g. observer summaries, retry counts).
    """

    execution_id: str
    steps: list[StepResult] = field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    total_duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)
