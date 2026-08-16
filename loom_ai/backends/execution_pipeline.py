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
"""

from __future__ import annotations

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

                # -- cancellation check --------------------------------------
                if context.cancelled:
                    step_results.append(
                        StepResult(step_id=step_id, status=StepStatus.CANCELLED)
                    )
                    continue

                # -- deadline check ------------------------------------------
                if context.deadline and self._deadline_exceeded(context.deadline):
                    step_results.append(
                        StepResult(
                            step_id=step_id,
                            status=StepStatus.CANCELLED,
                            error="deadline exceeded",
                        )
                    )
                    context.cancelled = True
                    continue

                # -- execute the step ----------------------------------------
                await self._notify_step_start(step_id, context)

                step_start = time.monotonic()
                try:
                    result = await step.execute(context)
                    elapsed_ms = (time.monotonic() - step_start) * 1000

                    # Ensure duration is populated.
                    if result.duration_ms == 0.0:
                        result = StepResult(
                            step_id=result.step_id or step_id,
                            status=result.status,
                            output=result.output,
                            duration_ms=elapsed_ms,
                            error=result.error,
                        )

                    step_results.append(result)
                    await self._notify_step_complete(step_id, result)

                    if result.status == StepStatus.FAILED:
                        had_failure = True
                        if self._fail_fast:
                            # Cancel remaining steps.
                            for remaining_idx in range(idx + 1, len(steps)):
                                step_results.append(
                                    StepResult(
                                        step_id=f"step-{remaining_idx}",
                                        status=StepStatus.CANCELLED,
                                    )
                                )
                            break

                except Exception as exc:
                    elapsed_ms = (time.monotonic() - step_start) * 1000
                    had_failure = True
                    error_result = StepResult(
                        step_id=step_id,
                        status=StepStatus.FAILED,
                        error=str(exc),
                        duration_ms=elapsed_ms,
                    )
                    step_results.append(error_result)
                    await self._notify_step_error(step_id, exc)

                    if self._fail_fast:
                        for remaining_idx in range(idx + 1, len(steps)):
                            step_results.append(
                                StepResult(
                                    step_id=f"step-{remaining_idx}",
                                    status=StepStatus.CANCELLED,
                                )
                            )
                        break

            # -- compute aggregate status ------------------------------------
            total_ms = (time.monotonic() - pipeline_start) * 1000
            status = self._derive_status(step_results, context.cancelled, had_failure)

            result = ExecutionResult(
                execution_id=context.execution_id,
                steps=step_results,
                status=status,
                total_duration_ms=total_ms,
            )
            await self._notify_execution_complete(result)
            return result
        finally:
            self._contexts.pop(context.execution_id, None)

    async def cancel(self, execution_id: str) -> bool:
        """Flag a running execution for cancellation.

        The pipeline checks this flag between steps, so the current step
        will finish before cancellation takes effect.
        """
        ctx = self._contexts.get(execution_id)
        if ctx is None:
            return False
        ctx.cancelled = True
        return True

    # -- internal helpers ----------------------------------------------------

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
