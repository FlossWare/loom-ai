"""Execution layer protocol contracts for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All methods are
async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

This module covers three contract areas:

- **ExecutionStep** -- a single executable unit in a pipeline (#210)
- **ExecutionPipeline** -- orchestrates a sequence of steps (#210)
- **ExecutionObserver** -- receives lifecycle notifications (#210)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_execution import (
        ExecutionContext,
        ExecutionResult,
        StepResult,
    )


# -- Execution Step (#210) ---------------------------------------------------


@runtime_checkable
class ExecutionStep(Protocol):
    """A single executable unit within an execution pipeline.

    Implementations receive an ``ExecutionContext`` and return a
    ``StepResult`` describing the outcome.
    """

    async def execute(self, context: ExecutionContext) -> StepResult:
        """Run this step within the given context."""
        ...


# -- Execution Pipeline (#210) -----------------------------------------------


@runtime_checkable
class ExecutionPipeline(Protocol):
    """Orchestrates a sequence of execution steps.

    Implementations are responsible for step ordering, cancellation,
    deadline enforcement, and observer notification.
    """

    async def run(
        self, steps: list[ExecutionStep], context: ExecutionContext
    ) -> ExecutionResult:
        """Execute *steps* in order within *context* and return the result."""
        ...

    async def cancel(self, execution_id: str) -> bool:
        """Request cancellation of a running execution.

        Returns ``True`` if the execution was found and flagged for
        cancellation, ``False`` otherwise.
        """
        ...


# -- Execution Observer (#210) -----------------------------------------------


@runtime_checkable
class ExecutionObserver(Protocol):
    """Receives lifecycle event notifications from an execution pipeline.

    Observers are notified at each step boundary and when the full
    execution completes.
    """

    async def on_step_start(self, step_id: str, context: ExecutionContext) -> None:
        """Called immediately before a step begins execution."""
        ...

    async def on_step_complete(self, step_id: str, result: StepResult) -> None:
        """Called when a step finishes successfully or is skipped."""
        ...

    async def on_step_error(self, step_id: str, error: Exception) -> None:
        """Called when a step raises an exception."""
        ...

    async def on_execution_complete(self, result: ExecutionResult) -> None:
        """Called when the full execution pipeline finishes."""
        ...
