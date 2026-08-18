"""Model-agnostic DAG execution engine for loom-ai.

Runs tasks in dependency order using topological waves.
Independent tasks execute concurrently via ``asyncio.gather``.
Failed tasks cancel pending transitive dependents but do not
block independent branches of the DAG.

Execution Hierarchy
-------------------
Loom's execution layer is composed of three levels:

1. **TaskRunner** (``loom_ai.protocols.TaskRunner``) -- the lowest-level
   primitive.  Runs a single ``Task`` and returns a result.

2. **ExecutionPipeline** (``loom_ai.contracts_execution.ExecutionPipeline``,
   implemented by ``loom_ai.backends.execution_pipeline.SequentialExecutionPipeline``)
   -- runs a flat sequence of ``ExecutionStep`` objects with lifecycle
   support (cancellation, deadlines, observers).  This is a sequential
   step runner, not a DAG orchestrator.

3. **ExecutionEngine** (this module) -- the highest-level component.
   Accepts an ``ExecutionPlan`` containing tasks with explicit
   dependencies, performs topological sorting, and executes independent
   tasks concurrently in waves.  Each task is dispatched through a
   ``TaskRunner``.

``ExecutionEngine`` and ``SequentialExecutionPipeline`` are complementary,
not competing.  The engine handles DAG decomposition and concurrency; the
pipeline handles flat sequential execution with operational concerns
(deadlines, cancellation).  A future integration could use a pipeline
instance to execute each wave's steps sequentially, composing the two
layers.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, cast

from loom_ai.config import LoomConfig
from loom_ai.models import ChatMessage, ExecutionPlan, Task, TaskStatus
from loom_ai.protocols import TaskRunner

TaskObserver = Callable[[Task, TaskStatus, TaskStatus], None]


class CyclicDependencyError(Exception):
    """The task dependency graph contains a cycle."""


class NoopTaskRunner:
    """Passes ``input_data`` through as ``output_data`` unchanged.

    Satisfies :class:`~loom_ai.protocols.TaskRunner` via structural
    subtyping. Useful for testing and pipeline scaffolding.
    """

    async def run(self, task: Task, config: LoomConfig) -> Any:
        return task.input_data


class LLMTaskRunner:
    """Minimal reference runner that sends a task to the configured LLM.

    This runner intentionally provides only the basic TaskRunner contract.
    Planning, tool use, agent loops, verification, and other richer runtime
    behavior belong in orchestration layers above this class.
    """

    async def run(self, task: Task, config: LoomConfig) -> Any:
        if config.llm is None:
            raise RuntimeError(
                "LLMTaskRunner requires an LLM backend. "
                "Set LOOM_LLM_BASE_URL or inject llm= "
                "into LoomConfig."
            )
        messages = [ChatMessage(role="user", content=task.description)]
        response = await config.llm.chat(messages)
        return {"response": response.content, "model": response.model}


class ExecutionEngine:
    """Dependency-aware task execution engine.

    Runs an :class:`ExecutionPlan` by repeatedly scheduling waves
    of ready tasks (all dependencies satisfied) in parallel.
    Failed tasks propagate cancellation to pending downstream dependents
    without blocking independent branches.
    """

    _DEFAULT_MAX_CONCURRENCY = 10

    def __init__(
        self,
        config: LoomConfig,
        runner: TaskRunner | None = None,
        observer: TaskObserver | None = None,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self._config = config
        self._runner: TaskRunner = runner or NoopTaskRunner()
        self._observer = observer
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_task(self, task: Task) -> Task:
        """Run a single task through the configured runner."""
        if task.status != TaskStatus.PENDING:
            raise ValueError(
                f"Cannot execute task {task.id!r} in {task.status.value!r} state"
            )
        task = self._transition(task, task.status, TaskStatus.RUNNING)
        try:
            async with self._semaphore:
                if task.timeout_seconds > 0:
                    result = await asyncio.wait_for(
                        self._runner.run(task, self._config),
                        timeout=task.timeout_seconds,
                    )
                else:
                    result = await self._runner.run(task, self._config)
            output = result if isinstance(result, dict) else {"result": result}
            task = replace(task, output_data=output)
            return self._transition(task, TaskStatus.RUNNING, TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            task = replace(task, error="task cancelled")
            self._transition(task, TaskStatus.RUNNING, TaskStatus.FAILED)
            raise
        except asyncio.TimeoutError:
            msg = f"Task {task.id!r} timed out after {task.timeout_seconds}s"
            task = replace(task, error=msg)
            return self._transition(task, TaskStatus.RUNNING, TaskStatus.FAILED)
        except Exception as exc:
            task = replace(task, error=str(exc))
            return self._transition(task, TaskStatus.RUNNING, TaskStatus.FAILED)

    async def execute_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Execute all tasks in the plan respecting dependencies.

        Tasks whose dependencies are all completed run in parallel.
        A failed task cancels its pending transitive dependents. Raises
        :class:`CyclicDependencyError` if unresolvable pending tasks remain.
        """
        task_map = {t.id: t for t in plan.tasks}
        self._validate_dependencies(plan.tasks, set(task_map))
        dependents = self._build_dependents_map(plan.tasks)

        while True:
            ready = [
                tid
                for tid, t in task_map.items()
                if t.status == TaskStatus.PENDING
                and all(
                    task_map[d].status == TaskStatus.COMPLETED for d in t.dependencies
                )
            ]
            if not ready:
                break

            ready.sort()
            results = await asyncio.gather(
                *(self.execute_task(task_map[tid]) for tid in ready)
            )
            for result in results:
                task_map[result.id] = result
                if result.status == TaskStatus.FAILED:
                    self._cancel_downstream(result.id, task_map, dependents)

        stuck = [t.id for t in task_map.values() if t.status == TaskStatus.PENDING]
        if stuck:
            raise CyclicDependencyError(
                "Cyclic dependency among tasks: " + ", ".join(sorted(stuck))
            )

        return cast(
            ExecutionPlan,
            replace(plan, tasks=[task_map[t.id] for t in plan.tasks]),
        )

    async def retry_failed(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Retry failed tasks and progressively release their dependents.

        Failed tasks with retries remaining are reset to ``PENDING`` and
        executed first. A cancelled dependent is only restored after *all*
        of its dependencies are actually ``COMPLETED``.
        """
        task_map = {t.id: t for t in plan.tasks}
        retried_any = False

        for task in plan.tasks:
            if task.status == TaskStatus.FAILED and task.retries_remaining > 0:
                task_map[task.id] = replace(
                    task,
                    status=TaskStatus.PENDING,
                    retries_remaining=task.retries_remaining - 1,
                    error="",
                    output_data={},
                    started_at="",
                    completed_at="",
                )
                retried_any = True

        if not retried_any:
            return plan

        updated: ExecutionPlan = cast(
            ExecutionPlan,
            replace(plan, tasks=[task_map[t.id] for t in plan.tasks]),
        )

        while True:
            updated = await self.execute_plan(updated)
            task_map = {t.id: t for t in updated.tasks}

            released = False
            for task in list(task_map.values()):
                if task.status != TaskStatus.CANCELLED:
                    continue
                deps_completed = all(
                    task_map[d].status == TaskStatus.COMPLETED
                    for d in task.dependencies
                )
                if deps_completed:
                    task_map[task.id] = replace(
                        task,
                        status=TaskStatus.PENDING,
                        error="",
                        output_data={},
                        started_at="",
                        completed_at="",
                    )
                    released = True

            if not released:
                return cast(
                    ExecutionPlan,
                    replace(
                        updated,
                        tasks=[task_map[t.id] for t in updated.tasks],
                    ),
                )

            updated = cast(
                ExecutionPlan,
                replace(
                    updated,
                    tasks=[task_map[t.id] for t in updated.tasks],
                ),
            )

    @staticmethod
    def _validate_dependencies(tasks: list[Task], all_ids: set[str]) -> None:
        """Raise if any task references an unknown dependency."""
        for task in tasks:
            unknown = set(task.dependencies) - all_ids
            if unknown:
                raise CyclicDependencyError(
                    f"Task {task.id!r} depends on unknown "
                    f"tasks: {', '.join(sorted(unknown))}"
                )

    @staticmethod
    def _build_dependents_map(
        tasks: list[Task],
    ) -> dict[str, set[str]]:
        """Return a mapping from task id to its direct dependents."""
        dependents: dict[str, set[str]] = defaultdict(set)
        for task in tasks:
            for dep_id in task.dependencies:
                dependents[dep_id].add(task.id)
        return dependents

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _transition(
        self,
        task: Task,
        old_status: TaskStatus,
        new_status: TaskStatus,
    ) -> Task:
        """Apply a status transition, set timestamps, fire observer."""
        updates: dict[str, Any] = {"status": new_status}
        if new_status == TaskStatus.RUNNING:
            updates["started_at"] = self._now()
        elif new_status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            updates["completed_at"] = self._now()
        updated = replace(task, **updates)
        if self._observer is not None:
            self._observer(updated, old_status, new_status)
        return updated

    def _cancel_downstream(
        self,
        failed_id: str,
        task_map: dict[str, Task],
        dependents: dict[str, set[str]],
    ) -> None:
        """Cancel pending tasks transitively dependent on *failed_id*.

        The execution engine processes whole waves before propagating
        failures, so downstream tasks should not be RUNNING here. Keeping
        cancellation limited to PENDING makes the state machine honest:
        a running coroutine is never marked CANCELLED without being cancelled.
        """
        queue = list(dependents.get(failed_id, set()))
        while queue:
            tid = queue.pop(0)
            task = task_map[tid]
            if task.status != TaskStatus.PENDING:
                continue
            task_map[tid] = self._transition(task, task.status, TaskStatus.CANCELLED)
            queue.extend(dependents.get(tid, set()))
