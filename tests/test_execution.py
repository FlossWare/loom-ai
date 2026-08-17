"""Tests for the execution engine: dependency resolution, parallelism,
failure handling, retry logic, and timeouts.
"""

import asyncio
from collections import defaultdict

import pytest

from loom_ai import (
    ExecutionEngine,
    ExecutionPlan,
    LoomConfig,
    NoopTaskRunner,
    Task,
    TaskStatus,
)
from loom_ai.execution import CyclicDependencyError


class RecordingRunner:
    """Tracks execution order and optionally fails specific tasks."""

    def __init__(self, fail_on_first: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.attempts: dict[str, int] = defaultdict(int)
        self._fail_on_first = fail_on_first or set()

    async def run(self, task, config):
        self.attempts[task.id] += 1
        self.calls.append(task.id)
        if task.id in self._fail_on_first and self.attempts[task.id] == 1:
            raise RuntimeError(f"Simulated failure: {task.id}")
        return {"attempt": self.attempts[task.id]}


class SlowRunner:
    """Sleeps longer than any reasonable timeout."""

    async def run(self, task, config):
        await asyncio.sleep(60)
        return {}


class FailingRunner:
    """Always raises an exception."""

    async def run(self, task, config):
        raise RuntimeError("Always fails")


async def test_linear_chain():
    """A -> B -> C executes in strict sequential order."""
    cfg = await LoomConfig.from_env()
    runner = RecordingRunner()
    engine = ExecutionEngine(cfg, runner=runner)
    plan = ExecutionPlan(
        id="linear",
        tasks=[
            Task(id="a", name="A"),
            Task(id="b", name="B", dependencies=["a"]),
            Task(id="c", name="C", dependencies=["b"]),
        ],
    )
    result = await engine.execute_plan(plan)
    assert all(t.status == TaskStatus.COMPLETED for t in result.tasks)
    assert runner.calls == ["a", "b", "c"]


async def test_parallel_independent_tasks():
    """Tasks with no dependencies all run in a single wave."""
    cfg = await LoomConfig.from_env()
    runner = RecordingRunner()
    engine = ExecutionEngine(cfg, runner=runner)
    plan = ExecutionPlan(
        id="parallel",
        tasks=[
            Task(id="x", name="X"),
            Task(id="y", name="Y"),
            Task(id="z", name="Z"),
        ],
    )
    result = await engine.execute_plan(plan)
    assert all(t.status == TaskStatus.COMPLETED for t in result.tasks)
    assert set(runner.calls) == {"x", "y", "z"}


async def test_diamond_dependency():
    """A -> (B, C) -> D executes in three waves."""
    cfg = await LoomConfig.from_env()
    runner = RecordingRunner()
    engine = ExecutionEngine(cfg, runner=runner)
    plan = ExecutionPlan(
        id="diamond",
        tasks=[
            Task(id="a", name="A"),
            Task(id="b", name="B", dependencies=["a"]),
            Task(id="c", name="C", dependencies=["a"]),
            Task(id="d", name="D", dependencies=["b", "c"]),
        ],
    )
    result = await engine.execute_plan(plan)
    statuses = {t.id: t.status for t in result.tasks}
    assert all(s == TaskStatus.COMPLETED for s in statuses.values())
    a_idx = runner.calls.index("a")
    b_idx = runner.calls.index("b")
    c_idx = runner.calls.index("c")
    d_idx = runner.calls.index("d")
    assert a_idx < b_idx
    assert a_idx < c_idx
    assert b_idx < d_idx
    assert c_idx < d_idx


async def test_failed_task_cancels_dependents():
    """A failing task cancels downstream dependents but not independent tasks."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg, runner=FailingRunner())
    plan = ExecutionPlan(
        id="fail-cascade",
        tasks=[
            Task(id="a", name="A"),
            Task(id="b", name="B", dependencies=["a"]),
            Task(id="c", name="C"),
        ],
    )
    result = await engine.execute_plan(plan)
    by_id = {t.id: t for t in result.tasks}
    assert by_id["a"].status == TaskStatus.FAILED
    assert by_id["a"].error == "Always fails"
    assert by_id["b"].status == TaskStatus.CANCELLED
    assert by_id["c"].status == TaskStatus.FAILED


async def test_failed_task_with_retry():
    """A task that fails on first attempt succeeds on retry."""
    cfg = await LoomConfig.from_env()
    runner = RecordingRunner(fail_on_first={"flaky"})
    engine = ExecutionEngine(cfg, runner=runner)
    plan = ExecutionPlan(
        id="retry",
        tasks=[
            Task(id="flaky", name="Flaky", retries_remaining=1),
            Task(id="after", name="After", dependencies=["flaky"]),
        ],
    )
    result = await engine.execute_plan(plan)
    by_id = {t.id: t for t in result.tasks}
    assert by_id["flaky"].status == TaskStatus.FAILED
    assert by_id["after"].status == TaskStatus.CANCELLED
    result = await engine.retry_failed(result)
    by_id = {t.id: t for t in result.tasks}
    assert by_id["flaky"].status == TaskStatus.COMPLETED
    assert by_id["after"].status == TaskStatus.COMPLETED
    assert runner.attempts["flaky"] == 2


async def test_retry_does_not_release_dependent_until_dependency_completes():
    """Cancelled work remains cancelled until every dependency completes."""
    cfg = await LoomConfig.from_env()
    runner = RecordingRunner(fail_on_first={"flaky"})
    engine = ExecutionEngine(cfg, runner=runner)
    plan = ExecutionPlan(
        id="retry-order",
        tasks=[
            Task(id="flaky", name="Flaky", retries_remaining=1),
            Task(id="other", name="Other", retries_remaining=1),
            Task(id="join", name="Join", dependencies=["flaky", "other"]),
        ],
    )
    result = await engine.execute_plan(plan)
    by_id = {t.id: t for t in result.tasks}
    assert by_id["join"].status == TaskStatus.CANCELLED

    # Both prerequisites must be completed before the cancelled join is released.
    result = await engine.retry_failed(result)
    by_id = {t.id: t for t in result.tasks}
    assert by_id["flaky"].status == TaskStatus.COMPLETED
    assert by_id["other"].status == TaskStatus.COMPLETED
    assert by_id["join"].status == TaskStatus.COMPLETED


async def test_retry_no_remaining_retries():
    """retry_failed returns plan unchanged when no retries left."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg, runner=FailingRunner())
    plan = ExecutionPlan(
        id="no-retries",
        tasks=[Task(id="a", name="A", retries_remaining=0)],
    )
    result = await engine.execute_plan(plan)
    assert result.tasks[0].status == TaskStatus.FAILED
    retried = await engine.retry_failed(result)
    assert retried.tasks[0].status == TaskStatus.FAILED


async def test_task_timeout():
    """A slow task is marked FAILED when it exceeds its timeout."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg, runner=SlowRunner())
    plan = ExecutionPlan(
        id="timeout",
        tasks=[Task(id="slow", name="Slow", timeout_seconds=0.05)],
    )
    result = await engine.execute_plan(plan)
    task = result.tasks[0]
    assert task.status == TaskStatus.FAILED
    assert task.error


async def test_cyclic_dependency_raises():
    """A cycle in the dependency graph raises CyclicDependencyError."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg)
    plan = ExecutionPlan(
        id="cycle",
        tasks=[
            Task(id="a", name="A", dependencies=["b"]),
            Task(id="b", name="B", dependencies=["a"]),
        ],
    )
    with pytest.raises(CyclicDependencyError):
        await engine.execute_plan(plan)


async def test_unknown_dependency_raises():
    """A dependency on a non-existent task raises an error."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg)
    plan = ExecutionPlan(
        id="unknown-dep",
        tasks=[Task(id="a", name="A", dependencies=["ghost"])],
    )
    with pytest.raises(CyclicDependencyError):
        await engine.execute_plan(plan)


async def test_observer_receives_transitions():
    """The observer callback fires for every status transition."""
    cfg = await LoomConfig.from_env()
    transitions: list[tuple[str, TaskStatus, TaskStatus]] = []

    def on_transition(task, old, new):
        transitions.append((task.id, old, new))

    engine = ExecutionEngine(cfg, runner=NoopTaskRunner(), observer=on_transition)
    plan = ExecutionPlan(id="observe", tasks=[Task(id="t", name="T")])
    await engine.execute_plan(plan)
    assert ("t", TaskStatus.PENDING, TaskStatus.RUNNING) in transitions
    assert ("t", TaskStatus.RUNNING, TaskStatus.COMPLETED) in transitions


async def test_empty_plan():
    """An empty plan executes without error."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg)
    plan = ExecutionPlan(id="empty", tasks=[])
    result = await engine.execute_plan(plan)
    assert result.tasks == []


async def test_single_task():
    """A plan with one task completes normally."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg)
    plan = ExecutionPlan(
        id="single",
        tasks=[Task(id="only", name="Only", input_data={"key": "value"})],
    )
    result = await engine.execute_plan(plan)
    task = result.tasks[0]
    assert task.status == TaskStatus.COMPLETED
    assert task.output_data == {"key": "value"}
    assert task.started_at != ""
    assert task.completed_at != ""


async def test_execute_task_rejects_non_pending():
    """execute_task raises ValueError for non-PENDING tasks."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg)
    task = Task(id="done", name="Done", status=TaskStatus.COMPLETED)
    with pytest.raises(ValueError, match="Cannot execute task"):
        await engine.execute_task(task)


async def test_task_preserves_order():
    """Returned plan preserves original task ordering."""
    cfg = await LoomConfig.from_env()
    engine = ExecutionEngine(cfg)
    plan = ExecutionPlan(
        id="order",
        tasks=[
            Task(id="c", name="C", dependencies=["a"]),
            Task(id="a", name="A"),
            Task(id="b", name="B", dependencies=["a"]),
        ],
    )
    result = await engine.execute_plan(plan)
    ids = [t.id for t in result.tasks]
    assert ids == ["c", "a", "b"]
