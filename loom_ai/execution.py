"""Model-agnostic execution engine for loom-ai.

Runs tasks in dependency order using topological waves.
Independent tasks execute concurrently via ``asyncio.gather``.
Failed tasks cancel their transitive dependents but do not
block independent branches of the DAG.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable

from loom_ai.config import LoomConfig
from loom_ai.models import (
    ChatMessage,
    ExecutionPlan,
    Task,
    TaskStatus,
)
from loom_ai.protocols import TaskRunner

TaskObserver = Callable[[Task, TaskStatus, TaskStatus], None]


class CyclicDependencyError(Exception):
    """The task dependency graph contains a cycle."""


# ── Built-in runners ────────────────────────────────────────────────────


class NoopTaskRunner:
    """Passes ``input_data`` through as ``output_data`` unchanged.

    Satisfies :class:`~loom_ai.protocols.TaskRunner` via structural
    subtyping.  Useful for testing and pipeline scaffolding.
    """

    async def run(self, task: Task, config: LoomConfig) -> Any:
        return task.input_data


class LLMTaskRunner:
    """Sends the task description to the configured LLM backend.

    Satisfies :class:`~loom_ai.protocols.TaskRunner` via structural
    subtyping.  Requires ``config.llm`` to be set.
    """

    async def run(self, task: Task, config: LoomConfig) -> Any:
        if config.llm is None:
            raise RuntimeError(
                "LLMTaskRunner requires an LLM backend. "
                "Set LOOM_LLM_BASE_URL or inject llm= "
                "into LoomConfig."
            )
        messages = [
            ChatMessage(role="user", content=task.description),
        ]
        response = await config.llm.chat(messages)
        return {
            "response": response.content,
            "model": response.model,
        }


# ── Execution engine ────────────────────────────────────────────────────


class ExecutionEngine:
    """Dependency-aware task execution engine.

    Runs an :class:`ExecutionPlan` by repeatedly scheduling waves
    of ready tasks (all dependencies satisfied) in parallel.
    Failed tasks propagate cancellations to downstream dependents
    without blocking independent branches.

    Parameters
    ----------
    config:
        Backend registry providing LLM access and other services.
    runner:
        Strategy for executing individual tasks.  Defaults to
        :class:`NoopTaskRunner` when ``None``.
    observer:
        Optional callback ``(task, old_status, new_status)``
        invoked on every task status transition.
    """

    def __init__(
        self,
        config: LoomConfig,
        runner: TaskRunner | None = None,
        observer: TaskObserver | None = None,
    ) -> None:
        self._config = config
        self._runner: TaskRunner = runner or NoopTaskRunner()
        self._observer = observer

    # ── Public API ──────────────────────────────────────────────────

    async def execute_task(self, task: Task) -> Task:
        """Run a single task through the configured runner.

        Transitions the task through RUNNING and then to either
        COMPLETED or FAILED.  Respects ``task.timeout_seconds``
        when set to a positive value.

        Raises ``ValueError`` if the task is not in PENDING state.
        """
        if task.status != TaskStatus.PENDING:
            raise ValueError(
                f"Cannot execute task {task.id!r} in "
                f"{task.status.value!r} state"
            )
        task = self._transition(
            task, task.status, TaskStatus.RUNNING
        )
        try:
            if task.timeout_seconds > 0:
                result = await asyncio.wait_for(
                    self._runner.run(task, self._config),
                    timeout=task.timeout_seconds,
                )
            else:
                result = await self._runner.run(
                    task, self._config
                )
            output = (
                result
                if isinstance(result, dict)
                else {"result": result}
            )
            task = replace(task, output_data=output)
            return self._transition(
                task, TaskStatus.RUNNING, TaskStatus.COMPLETED
            )
        except asyncio.TimeoutError:
            msg = (
                f"Task {task.id!r} timed out after "
                f"{task.timeout_seconds}s"
            )
            task = replace(task, error=msg)
            return self._transition(
                task, TaskStatus.RUNNING, TaskStatus.FAILED
            )
        except Exception as exc:
            task = replace(task, error=str(exc))
            return self._transition(
                task, TaskStatus.RUNNING, TaskStatus.FAILED
            )

    async def execute_plan(
        self, plan: ExecutionPlan
    ) -> ExecutionPlan:
        """Execute all tasks in the plan respecting dependencies.

        Tasks whose dependencies are all completed run in parallel.
        A failed task cancels its transitive dependents.  Raises
        :class:`CyclicDependencyError` if unresolvable tasks remain.
        """
        task_map = {t.id: t for t in plan.tasks}
        all_ids = set(task_map)

        for task in plan.tasks:
            unknown = set(task.dependencies) - all_ids
            if unknown:
                raise CyclicDependencyError(
                    f"Task {task.id!r} depends on unknown "
                    f"tasks: {', '.join(sorted(unknown))}"
                )

        dependents: dict[str, set[str]] = defaultdict(set)
        for task in plan.tasks:
            for dep_id in task.dependencies:
                dependents[dep_id].add(task.id)

        while True:
            ready = [
                tid
                for tid, t in task_map.items()
                if t.status == TaskStatus.PENDING
                and all(
                    task_map[d].status == TaskStatus.COMPLETED
                    for d in t.dependencies
                )
            ]
            if not ready:
                break

            ready.sort()
            results = await asyncio.gather(
                *(
                    self.execute_task(task_map[tid])
                    for tid in ready
                )
            )
            for result in results:
                task_map[result.id] = result
                if result.status == TaskStatus.FAILED:
                    self._cancel_downstream(
                        result.id, task_map, dependents
                    )

        stuck = [
            t.id
            for t in task_map.values()
            if t.status == TaskStatus.PENDING
        ]
        if stuck:
            raise CyclicDependencyError(
                "Cyclic dependency among tasks: "
                + ", ".join(sorted(stuck))
            )

        return replace(
            plan,
            tasks=[task_map[t.id] for t in plan.tasks],
        )

    async def retry_failed(
        self, plan: ExecutionPlan
    ) -> ExecutionPlan:
        """Retry all failed tasks that have retries remaining.

        Resets failed tasks (with ``retries_remaining > 0``) to
        PENDING, un-cancels downstream tasks whose dependencies
        are now satisfiable, then re-executes the updated plan.
        Returns the plan unchanged when nothing is retryable.
        """
        task_map = {t.id: t for t in plan.tasks}
        retried_any = False

        for task in plan.tasks:
            if (
                task.status == TaskStatus.FAILED
                and task.retries_remaining > 0
            ):
                task_map[task.id] = replace(
                    task,
                    status=TaskStatus.PENDING,
                    retries_remaining=(
                        task.retries_remaining - 1
                    ),
                    error="",
                    output_data={},
                    started_at="",
                    completed_at="",
                )
                retried_any = True

        if not retried_any:
            return plan

        changed = True
        while changed:
            changed = False
            for task in list(task_map.values()):
                if task.status != TaskStatus.CANCELLED:
                    continue
                deps_ok = all(
                    task_map[d].status
                    in (
                        TaskStatus.COMPLETED,
                        TaskStatus.PENDING,
                    )
                    for d in task.dependencies
                )
                if deps_ok:
                    task_map[task.id] = replace(
                        task,
                        status=TaskStatus.PENDING,
                        error="",
                        output_data={},
                        started_at="",
                        completed_at="",
                    )
                    changed = True

        updated = replace(
            plan,
            tasks=[task_map[t.id] for t in plan.tasks],
        )
        return await self.execute_plan(updated)

    # ── Internal helpers ────────────────────────────────────────────

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
        """Cancel all tasks transitively dependent on *failed_id*."""
        queue = list(dependents.get(failed_id, set()))
        while queue:
            tid = queue.pop(0)
            task = task_map[tid]
            if task.status not in (
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
            ):
                continue
            task_map[tid] = self._transition(
                task, task.status, TaskStatus.CANCELLED
            )
            queue.extend(dependents.get(tid, set()))
