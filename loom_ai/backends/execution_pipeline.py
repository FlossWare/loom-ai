"""Sequential execution pipeline backend for loom-ai.

Runs a list of :class:`~loom_ai.contracts_execution.ExecutionStep` objects
one after another, checking for cancellation and deadline expiry between
steps.  Observer notifications are emitted at each lifecycle boundary.

Two failure modes are supported:

- **fail-fast** (default) -- the pipeline stops at the first step failure
  and marks remaining steps as ``CANCELLED``.
- **continue** -- the pipeline records the failure and proceeds to the
  next step.

Zero external dependencies -- stdlib only.

Relationship to ExecutionEngine
-------------------------------
This pipeline is a **sequential step runner** -- it executes a flat list
of steps one at a time with operational lifecycle support (cancellation,
deadlines, observers).  It does *not* handle dependency graphs or
concurrent execution.

The DAG-aware :class:`~loom_ai.execution.ExecutionEngine` is the
higher-level orchestrator.  It resolves task dependencies via topological
sorting and dispatches independent tasks concurrently in waves, using a
:class:`~loom_ai.protocols.TaskRunner` for individual task execution.

The intended layering is::

    ExecutionEngine        (DAG orchestration, topological waves)
      +-- ExecutionPipeline  (sequential step runner, this module)
            +-- TaskRunner   (single task execution primitive)

Both components are complementary: the engine decomposes a DAG into
sequential waves; this pipeline (or a similar implementation) can run
each wave's steps with deadline and cancellation support.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from loom_ai.models_execution import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    StepResult,
    StepStatus,
)


class SequentialExecutionPipeline:
    """Execute steps one at a time with cancellation and deadline support.

    Satisfies :class:`~loom_ai.contracts_execution.ExecutionPipeline` via
    structural subtyping.

    Parameters
    ----------
    fail_fast:
        When ``True`` (the default), execution halts on the first step
        failure.  When ``False``, all steps are attempted regardless of
        earlier failures.
    observers:
        Optional list of objects satisfying
        :class:`~loom_ai.contracts_execution.ExecutionObserver`.  Each
        observer is notified at every lifecycle boundary.
    """

    def __init__(
        self,
        *,
        fail_fast: bool = True,
        observers: list[Any] | None = None,
    ) -> None:
        self._fail_fast = fail_fast
        self._observers: list[Any] = list(observers) if observers else []
        self._contexts: dict[str, ExecutionContext] = {}

    # -- ExecutionPipeline interface -----------------------------------------

    async def run(self, steps: list[Any], context: ExecutionContext) -> ExecutionResult:
        """Execute *steps* sequentially within *context*.

        Returns an :class:`ExecutionResult` summarising the full run.
        """
        self._contexts[context.execution_id] = context
        pipeline_start = time.monotonic()
        step_results: list[StepResult] = []
        had_failure = False

        try:
            for idx, step in enumerate(steps):
                step_id = f"step-{idx}"

                if self._should_skip(context):
                    step_results.append(self._make_skip_result(step_id, context))
                    continue

                await self._notify_step_start(step_id, context)
                result, failed = await self._execute_step(step, step_id, context)
                step_results.append(result)

                if failed:
                    had_failure = True
                    if self._fail_fast:
                        self._cancel_remaining(idx, len(steps), step_results)
                        break

            total_ms = (time.monotonic() - pipeline_start) * 1000
            status = self._derive_status(step_results, context.cancelled, had_failure)

            execution_result = ExecutionResult(
                execution_id=context.execution_id,
                steps=step_results,
                status=status,
                total_duration_ms=total_ms,
            )
            await self._notify_execution_complete(execution_result)
            return execution_result
        finally:
            self._contexts.pop(context.execution_id, None)

    async def cancel(self, execution_id: str) -> bool:
        """Flag a running execution for cancellation.

        The pipeline checks this flag between steps, so the current step
        will finish before cancellation takes effect.
        """
        await asyncio.sleep(0)
        ctx = self._contexts.get(execution_id)
        if ctx is None:
            return False
        ctx.cancelled = True
        return True

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _should_skip(context: ExecutionContext) -> bool:
        """Return True if the step should be skipped (cancelled or past deadline)."""
        if context.cancelled:
            return True
        if context.deadline:
            return SequentialExecutionPipeline._deadline_exceeded(context.deadline)
        return False

    @staticmethod
    def _make_skip_result(step_id: str, context: ExecutionContext) -> StepResult:
        """Create a CANCELLED StepResult, setting the deadline flag if needed."""
        if not context.cancelled and context.deadline:
            context.cancelled = True
            return StepResult(
                step_id=step_id,
                status=StepStatus.CANCELLED,
                error="deadline exceeded",
            )
        return StepResult(step_id=step_id, status=StepStatus.CANCELLED)

    async def _execute_step(
        self, step: Any, step_id: str, context: ExecutionContext
    ) -> tuple[StepResult, bool]:
        """Run a single step and return ``(result, failed)``."""
        step_start = time.monotonic()
        try:
            result = await step.execute(context)
            elapsed_ms = (time.monotonic() - step_start) * 1000

            if result.duration_ms <= 0:
                result = StepResult(
                    step_id=result.step_id or step_id,
                    status=result.status,
                    output=result.output,
                    duration_ms=elapsed_ms,
                    error=result.error,
                )

            await self._notify_step_complete(step_id, result)
            return result, result.status == StepStatus.FAILED

        except Exception as exc:
            elapsed_ms = (time.monotonic() - step_start) * 1000
            error_result = StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(exc),
                duration_ms=elapsed_ms,
            )
            await self._notify_step_error(step_id, exc)
            return error_result, True

    @staticmethod
    def _cancel_remaining(
        current_idx: int, total: int, results: list[StepResult]
    ) -> None:
        """Append CANCELLED results for all steps after *current_idx*."""
        for remaining_idx in range(current_idx + 1, total):
            results.append(
                StepResult(
                    step_id=f"step-{remaining_idx}",
                    status=StepStatus.CANCELLED,
                )
            )

    @staticmethod
    def _deadline_exceeded(deadline: str) -> bool:
        """Return ``True`` if the ISO-8601 *deadline* is in the past."""
        try:
            dt = datetime.fromisoformat(deadline)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= dt
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _derive_status(
        results: list[StepResult], cancelled: bool, had_failure: bool
    ) -> ExecutionStatus:
        """Derive an aggregate status from individual step results."""
        if cancelled:
            return ExecutionStatus.CANCELLED

        if not results:
            return ExecutionStatus.SUCCESS

        if had_failure:
            has_success = any(r.status == StepStatus.SUCCESS for r in results)
            if not has_success:
                # No step succeeded -- the entire run failed.
                return ExecutionStatus.FAILED
            has_cancelled = any(r.status == StepStatus.CANCELLED for r in results)
            if has_cancelled:
                # A failure caused remaining steps to be cancelled
                # (fail-fast) -- treat as overall failure.
                return ExecutionStatus.FAILED
            # Some steps succeeded and some failed, none cancelled.
            return ExecutionStatus.PARTIAL

        return ExecutionStatus.SUCCESS

    # -- observer dispatch ---------------------------------------------------

    async def _notify_step_start(self, step_id: str, context: ExecutionContext) -> None:
        for obs in self._observers:
            await obs.on_step_start(step_id, context)

    async def _notify_step_complete(self, step_id: str, result: StepResult) -> None:
        for obs in self._observers:
            await obs.on_step_complete(step_id, result)

    async def _notify_step_error(self, step_id: str, error: Exception) -> None:
        for obs in self._observers:
            await obs.on_step_error(step_id, error)

    async def _notify_execution_complete(self, result: ExecutionResult) -> None:
        for obs in self._observers:
            await obs.on_execution_complete(result)
