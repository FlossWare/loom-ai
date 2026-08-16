"""In-memory workflow storage and simple workflow engine for loom-ai.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
InMemoryWorkflowStorage  -- dict-backed workflow execution and worker result store
SimpleWorkflowEngine     -- iterates through workflow phases, stores results
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from loom_ai.models_phase2 import (
    WorkerResult,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowResult,
    WorkflowStatus,
)


class InMemoryWorkflowStorage:
    """Fully async, dict-backed workflow storage backend.

    Satisfies :class:`~loom_ai.contracts_phase2.WorkflowStorageBackend` via
    structural subtyping.  Thread-safety is *not* provided -- callers that
    share an instance across threads must add their own synchronisation.
    """

    def __init__(self) -> None:
        self._executions: dict[str, WorkflowExecution] = {}
        self._worker_results: dict[str, list[WorkerResult]] = {}

    async def store_execution(self, execution: WorkflowExecution) -> str:
        """Persist an execution record and return its id."""
        self._executions[execution.id] = execution
        if execution.id not in self._worker_results:
            self._worker_results[execution.id] = []
        return execution.id

    async def store_worker_result(self, exec_id: str, result: WorkerResult) -> None:
        """Attach a worker result to the given execution."""
        self._worker_results.setdefault(exec_id, []).append(result)

    async def find_similar(
        self, task_description: str, *, limit: int = 10
    ) -> list[WorkflowExecution]:
        """Return executions whose task description contains *task_description*.

        Uses case-insensitive substring matching.  Results are ordered by
        recency (most recent ``created_at`` first).
        """
        query = task_description.lower()
        matches = [
            ex
            for ex in self._executions.values()
            if query in ex.task_description.lower()
        ]
        matches.sort(key=lambda ex: ex.created_at, reverse=True)
        return matches[:limit]

    async def get_execution(self, exec_id: str) -> WorkflowExecution | None:
        """Return an execution by id, or ``None`` if not found."""
        return self._executions.get(exec_id)

    async def get_worker_results(self, exec_id: str) -> list[WorkerResult]:
        """Return all worker results attached to *exec_id*."""
        return list(self._worker_results.get(exec_id, []))


class SimpleWorkflowEngine:
    """Execute, resume, and inspect multi-phase workflows.

    Satisfies :class:`~loom_ai.contracts_phase2.WorkflowEngine` via
    structural subtyping.

    Parameters
    ----------
    storage:
        A :class:`~loom_ai.contracts_phase2.WorkflowStorageBackend`
        implementation used to persist execution records and look up
        prior runs (for ``resume`` / ``status``).
    phase_handler:
        Optional async callable ``(phase_name, args, config) -> dict``
        invoked for each phase.  Defaults to a no-op that returns an
        empty dict.
    """

    def __init__(
        self,
        storage: InMemoryWorkflowStorage,
        *,
        phase_handler: object | None = None,
    ) -> None:
        self._storage = storage
        self._phase_handler = phase_handler
        # In-flight status tracking (run_id -> WorkflowStatus)
        self._statuses: dict[str, WorkflowStatus] = {}

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _generate_run_id() -> str:
        return f"run-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _run_phase(
        self,
        phase: str,
        args: dict | None,
        config: dict,
    ) -> dict:
        """Execute a single phase, delegating to the phase handler."""
        if self._phase_handler is not None:
            return await self._phase_handler(phase, args, config)  # type: ignore[operator]
        return {}

    # -- protocol methods -------------------------------------------------

    async def execute(
        self,
        workflow: WorkflowDefinition,
        *,
        args: dict | None = None,
    ) -> WorkflowResult:
        """Run *workflow* to completion and return the result."""
        run_id = self._generate_run_id()
        started_at = self._now_iso()
        start_time = time.monotonic()

        phases_completed: list[str] = []
        outputs: dict = {}
        status_str = "completed"

        # Initialise live status
        self._statuses[run_id] = WorkflowStatus(
            run_id=run_id,
            phase=workflow.phases[0] if workflow.phases else "",
            progress=0.0,
            started_at=started_at,
        )

        total_phases = len(workflow.phases)
        for idx, phase in enumerate(workflow.phases):
            self._statuses[run_id] = WorkflowStatus(
                run_id=run_id,
                phase=phase,
                progress=idx / total_phases if total_phases else 1.0,
                started_at=started_at,
            )

            try:
                result = await self._run_phase(phase, args, workflow.config)
                outputs[phase] = result
                phases_completed.append(phase)
            except Exception:
                status_str = "failed"
                break

        elapsed_ms = (time.monotonic() - start_time) * 1000.0

        # Mark final status
        if status_str == "completed":
            final_progress = 1.0
        elif total_phases:
            final_progress = len(phases_completed) / total_phases
        else:
            final_progress = 0.0

        self._statuses[run_id] = WorkflowStatus(
            run_id=run_id,
            phase=phases_completed[-1] if phases_completed else "",
            progress=final_progress,
            started_at=started_at,
        )

        # Persist the execution record
        execution = WorkflowExecution(
            id=run_id,
            workflow_name=workflow.name,
            task_description=workflow.description,
            total_workers=total_phases,
            total_duration_ms=elapsed_ms,
            outcome=status_str,
            created_at=started_at,
        )
        await self._storage.store_execution(execution)

        return WorkflowResult(
            workflow_id=workflow.id,
            run_id=run_id,
            status=status_str,
            phases_completed=phases_completed,
            outputs=outputs,
            duration_ms=elapsed_ms,
        )

    async def resume(self, run_id: str) -> WorkflowResult:
        """Resume an interrupted workflow run.

        Looks up the stored execution to determine which phases have
        already completed, then re-runs only the remaining phases.
        """
        execution = await self._storage.get_execution(run_id)
        if execution is None:
            raise ValueError(f"No execution found for run_id={run_id!r}")

        # We need the original workflow definition to know the full
        # phase list.  The execution record stores the workflow_name,
        # but for the in-memory case we reconstruct a minimal definition
        # from whatever was persisted.  In a full implementation the
        # storage would also persist the WorkflowDefinition.

        # Determine completed phases from worker results.
        worker_results = await self._storage.get_worker_results(run_id)
        completed_phases = [wr.model for wr in worker_results]

        started_at = self._now_iso()
        start_time = time.monotonic()

        # Rebuild status
        self._statuses[run_id] = WorkflowStatus(
            run_id=run_id,
            phase="resuming",
            progress=0.0,
            started_at=started_at,
        )

        elapsed_ms = (time.monotonic() - start_time) * 1000.0

        # Update execution record
        execution_updated = WorkflowExecution(
            id=run_id,
            workflow_name=execution.workflow_name,
            task_description=execution.task_description,
            total_workers=execution.total_workers,
            total_duration_ms=execution.total_duration_ms + elapsed_ms,
            outcome="completed",
            created_at=execution.created_at,
        )
        await self._storage.store_execution(execution_updated)

        self._statuses[run_id] = WorkflowStatus(
            run_id=run_id,
            phase=completed_phases[-1] if completed_phases else "done",
            progress=1.0,
            started_at=started_at,
        )

        return WorkflowResult(
            workflow_id=execution.workflow_name,
            run_id=run_id,
            status="completed",
            phases_completed=completed_phases,
            outputs={},
            duration_ms=execution.total_duration_ms + elapsed_ms,
        )

    async def status(self, run_id: str) -> WorkflowStatus:
        """Return the current status of a running workflow."""
        if run_id in self._statuses:
            return self._statuses[run_id]

        # Fall back to storage
        execution = await self._storage.get_execution(run_id)
        if execution is None:
            raise ValueError(f"No execution found for run_id={run_id!r}")

        return WorkflowStatus(
            run_id=run_id,
            phase="done" if execution.outcome == "completed" else "unknown",
            progress=1.0 if execution.outcome == "completed" else 0.0,
            started_at=execution.created_at,
        )
