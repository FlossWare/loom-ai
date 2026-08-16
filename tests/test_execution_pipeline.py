"""Tests for the execution pipeline layer: sequential execution,
cancellation, deadlines, failure modes, observers, and protocol
conformance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from loom_ai.backends.execution_pipeline import SequentialExecutionPipeline
from loom_ai.contracts_execution import (
    ExecutionObserver,
    ExecutionPipeline,
    ExecutionStep,
)
from loom_ai.models_execution import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    StepResult,
    StepStatus,
)

# ── Stub steps ─────────────────────────────────────────────────────────


class SuccessStep:
    """A step that always succeeds with configurable output."""

    def __init__(self, output: dict | None = None) -> None:
        self._output = output or {"ok": True}

    async def execute(self, context: ExecutionContext) -> StepResult:
        _ = context
        return StepResult(step_id="", status=StepStatus.SUCCESS, output=self._output)


class FailingStep:
    """A step that always raises an exception."""

    def __init__(self, message: str = "step failed") -> None:
        self._message = message

    async def execute(self, context: ExecutionContext) -> StepResult:
        _ = context
        raise RuntimeError(self._message)


class ReturnsFailedStep:
    """A step that returns a FAILED StepResult without raising."""

    async def execute(self, context: ExecutionContext) -> StepResult:
        _ = context
        return StepResult(step_id="", status=StepStatus.FAILED, error="soft failure")


class SlowStep:
    """A step that sleeps for a configurable duration."""

    def __init__(self, seconds: float = 1.0) -> None:
        self._seconds = seconds

    async def execute(self, context: ExecutionContext) -> StepResult:
        _ = context
        await asyncio.sleep(self._seconds)
        return StepResult(step_id="", status=StepStatus.SUCCESS)


class RecordingStep:
    """A step that records the execution_id it received."""

    def __init__(self) -> None:
        self.seen_ids: list[str] = []

    async def execute(self, context: ExecutionContext) -> StepResult:
        self.seen_ids.append(context.execution_id)
        return StepResult(step_id="", status=StepStatus.SUCCESS)


# ── Recording observer ─────────────────────────────────────────────────


class RecordingObserver:
    """Captures all observer events for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []

    async def on_step_start(self, step_id: str, context: ExecutionContext) -> None:
        _ = context
        self.events.append(("step_start", step_id))

    async def on_step_complete(self, step_id: str, result: StepResult) -> None:
        _ = result
        self.events.append(("step_complete", step_id))

    async def on_step_error(self, step_id: str, error: Exception) -> None:
        _ = error
        self.events.append(("step_error", step_id))

    async def on_execution_complete(self, result: ExecutionResult) -> None:
        _ = result
        self.events.append(("execution_complete",))


# ── Tests ──────────────────────────────────────────────────────────────


async def test_sequential_multiple_steps():
    """Multiple successful steps run in order."""
    pipeline = SequentialExecutionPipeline()
    ctx = ExecutionContext(execution_id="run-1", inputs={"x": 1})
    steps = [SuccessStep({"a": 1}), SuccessStep({"b": 2}), SuccessStep({"c": 3})]

    result = await pipeline.run(steps, ctx)

    assert result.execution_id == "run-1"
    assert result.status == ExecutionStatus.SUCCESS
    assert len(result.steps) == 3
    assert all(s.status == StepStatus.SUCCESS for s in result.steps)
    assert result.steps[0].output == {"a": 1}
    assert result.steps[1].output == {"b": 2}
    assert result.steps[2].output == {"c": 3}
    assert result.total_duration_ms > 0


async def test_cancellation_mid_execution():
    """Setting cancelled=True stops execution after the current step."""
    pipeline = SequentialExecutionPipeline()
    ctx = ExecutionContext(execution_id="cancel-1")

    class CancellingStep:
        async def execute(self, context: ExecutionContext) -> StepResult:
            context.cancelled = True
            return StepResult(step_id="", status=StepStatus.SUCCESS)

    steps = [CancellingStep(), SuccessStep(), SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.status == ExecutionStatus.CANCELLED
    assert result.steps[0].status == StepStatus.SUCCESS
    assert result.steps[1].status == StepStatus.CANCELLED
    assert result.steps[2].status == StepStatus.CANCELLED


async def test_cancel_via_method():
    """The cancel() method flags an in-flight execution."""
    pipeline = SequentialExecutionPipeline()
    ctx = ExecutionContext(execution_id="cancel-method")

    class SlowThenCheck:
        async def execute(self, context: ExecutionContext) -> StepResult:
            _ = context
            await asyncio.sleep(0.05)
            return StepResult(step_id="", status=StepStatus.SUCCESS)

    async def cancel_soon():
        await asyncio.sleep(0.01)
        found = await pipeline.cancel("cancel-method")
        assert found is True

    steps = [SlowThenCheck(), SuccessStep()]
    _, result = await asyncio.gather(cancel_soon(), pipeline.run(steps, ctx))

    cancelled_count = sum(1 for s in result.steps if s.status == StepStatus.CANCELLED)
    assert cancelled_count >= 1


async def test_cancel_unknown_execution():
    """cancel() returns False for an unknown execution_id."""
    pipeline = SequentialExecutionPipeline()
    assert await pipeline.cancel("nonexistent") is False


async def test_deadline_expiration():
    """A deadline in the past causes remaining steps to be cancelled."""
    pipeline = SequentialExecutionPipeline()
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    ctx = ExecutionContext(execution_id="deadline-1", deadline=past)

    steps = [SuccessStep(), SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.status == ExecutionStatus.CANCELLED
    assert result.steps[0].status == StepStatus.CANCELLED
    assert result.steps[0].error == "deadline exceeded"


async def test_deadline_future_does_not_cancel():
    """A deadline far in the future does not affect execution."""
    pipeline = SequentialExecutionPipeline()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    ctx = ExecutionContext(execution_id="deadline-ok", deadline=future)

    steps = [SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.steps[0].status == StepStatus.SUCCESS


async def test_step_failure_fail_fast():
    """In fail-fast mode, a failing step cancels all remaining steps."""
    pipeline = SequentialExecutionPipeline(fail_fast=True)
    ctx = ExecutionContext(execution_id="ff-1")

    steps = [SuccessStep(), FailingStep("boom"), SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.steps[0].status == StepStatus.SUCCESS
    assert result.steps[1].status == StepStatus.FAILED
    assert "boom" in result.steps[1].error
    assert result.steps[2].status == StepStatus.CANCELLED
    assert result.status == ExecutionStatus.FAILED


async def test_step_failure_continue():
    """In continue mode, execution proceeds past failures."""
    pipeline = SequentialExecutionPipeline(fail_fast=False)
    ctx = ExecutionContext(execution_id="cont-1")

    steps = [SuccessStep(), FailingStep("oops"), SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.steps[0].status == StepStatus.SUCCESS
    assert result.steps[1].status == StepStatus.FAILED
    assert result.steps[2].status == StepStatus.SUCCESS
    assert result.status == ExecutionStatus.PARTIAL


async def test_soft_failure_fail_fast():
    """A step returning FAILED status (no exception) also triggers fail-fast."""
    pipeline = SequentialExecutionPipeline(fail_fast=True)
    ctx = ExecutionContext(execution_id="soft-ff")

    steps = [ReturnsFailedStep(), SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.steps[0].status == StepStatus.FAILED
    assert result.steps[1].status == StepStatus.CANCELLED
    assert result.status == ExecutionStatus.FAILED


async def test_observer_notifications():
    """Observers receive events for each step and the execution."""
    observer = RecordingObserver()
    pipeline = SequentialExecutionPipeline(observers=[observer])
    ctx = ExecutionContext(execution_id="obs-1")

    steps = [SuccessStep(), SuccessStep()]
    await pipeline.run(steps, ctx)

    assert ("step_start", "step-0") in observer.events
    assert ("step_complete", "step-0") in observer.events
    assert ("step_start", "step-1") in observer.events
    assert ("step_complete", "step-1") in observer.events
    assert ("execution_complete",) in observer.events


async def test_observer_error_notification():
    """Observers receive on_step_error when a step raises."""
    observer = RecordingObserver()
    pipeline = SequentialExecutionPipeline(fail_fast=True, observers=[observer])
    ctx = ExecutionContext(execution_id="obs-err")

    steps = [FailingStep("kaboom")]
    await pipeline.run(steps, ctx)

    assert ("step_start", "step-0") in observer.events
    assert ("step_error", "step-0") in observer.events
    assert ("execution_complete",) in observer.events


async def test_step_duration_recorded():
    """Each step result has a non-zero duration_ms."""
    pipeline = SequentialExecutionPipeline()
    ctx = ExecutionContext(execution_id="dur-1")

    steps = [SuccessStep()]
    result = await pipeline.run(steps, ctx)

    assert result.steps[0].duration_ms > 0


async def test_empty_pipeline():
    """An empty list of steps produces a successful result."""
    pipeline = SequentialExecutionPipeline()
    ctx = ExecutionContext(execution_id="empty-1")

    result = await pipeline.run([], ctx)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.steps == []
    assert result.execution_id == "empty-1"


async def test_context_inputs_available_to_steps():
    """Steps receive the execution context including inputs."""
    recorder = RecordingStep()
    pipeline = SequentialExecutionPipeline()
    ctx = ExecutionContext(execution_id="ctx-1", inputs={"key": "val"})

    await pipeline.run([recorder], ctx)

    assert recorder.seen_ids == ["ctx-1"]


async def test_all_steps_fail():
    """When every step fails, the overall status is FAILED."""
    pipeline = SequentialExecutionPipeline(fail_fast=False)
    ctx = ExecutionContext(execution_id="all-fail")

    steps = [FailingStep("a"), FailingStep("b")]
    result = await pipeline.run(steps, ctx)

    assert result.status == ExecutionStatus.FAILED
    assert all(s.status == StepStatus.FAILED for s in result.steps)


# ── Protocol conformance ──────────────────────────────────────────────


async def test_protocol_conformance_execution_step():
    """SuccessStep satisfies the ExecutionStep protocol."""
    assert isinstance(SuccessStep(), ExecutionStep)


async def test_protocol_conformance_execution_pipeline():
    """SequentialExecutionPipeline satisfies the ExecutionPipeline protocol."""
    assert isinstance(SequentialExecutionPipeline(), ExecutionPipeline)


async def test_protocol_conformance_execution_observer():
    """RecordingObserver satisfies the ExecutionObserver protocol."""
    assert isinstance(RecordingObserver(), ExecutionObserver)
