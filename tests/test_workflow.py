"""Tests for workflow engine and in-memory workflow storage.

Covers: execute, resume, status, storage CRUD, find_similar.
No external dependencies required.
"""

from __future__ import annotations

import pytest

from loom_ai.backends.workflow import InMemoryWorkflowStorage, SimpleWorkflowEngine
from loom_ai.models_phase2 import (
    WorkerResult,
    WorkflowDefinition,
    WorkflowExecution,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _make_definition(
    *,
    phases: list[str] | None = None,
    name: str = "test-wf",
    description: str = "A test workflow",
) -> WorkflowDefinition:
    return WorkflowDefinition(
        id="wf-1",
        name=name,
        description=description,
        phases=["plan", "execute", "review"] if phases is None else phases,
    )


def _make_execution(
    *,
    exec_id: str = "exec-1",
    name: str = "test-wf",
    description: str = "test task",
    outcome: str = "completed",
) -> WorkflowExecution:
    return WorkflowExecution(
        id=exec_id,
        workflow_name=name,
        task_description=description,
        total_workers=3,
        total_duration_ms=100.0,
        outcome=outcome,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _make_worker_result(
    *,
    result_id: str = "wr-1",
    exec_id: str = "exec-1",
    model: str = "plan",
) -> WorkerResult:
    return WorkerResult(
        id=result_id,
        execution_id=exec_id,
        model=model,
        content="output",
        latency_ms=50.0,
        tokens_used=100,
        success=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# InMemoryWorkflowStorage
# ═══════════════════════════════════════════════════════════════════════


class TestInMemoryWorkflowStorage:
    """Unit tests for the in-memory workflow storage backend."""

    async def test_store_and_get_execution(self):
        storage = InMemoryWorkflowStorage()
        ex = _make_execution()
        returned_id = await storage.store_execution(ex)
        assert returned_id == "exec-1"

        fetched = await storage.get_execution("exec-1")
        assert fetched is not None
        assert fetched.workflow_name == "test-wf"
        assert fetched.outcome == "completed"

    async def test_get_execution_not_found(self):
        storage = InMemoryWorkflowStorage()
        result = await storage.get_execution("nonexistent")
        assert result is None

    async def test_store_worker_result(self):
        storage = InMemoryWorkflowStorage()
        ex = _make_execution()
        await storage.store_execution(ex)

        wr = _make_worker_result()
        await storage.store_worker_result("exec-1", wr)

        results = await storage.get_worker_results("exec-1")
        assert len(results) == 1
        assert results[0].model == "plan"

    async def test_store_multiple_worker_results(self):
        storage = InMemoryWorkflowStorage()
        ex = _make_execution()
        await storage.store_execution(ex)

        for i, model in enumerate(["plan", "execute", "review"]):
            wr = _make_worker_result(result_id=f"wr-{i}", model=model)
            await storage.store_worker_result("exec-1", wr)

        results = await storage.get_worker_results("exec-1")
        assert len(results) == 3
        assert [r.model for r in results] == ["plan", "execute", "review"]

    async def test_get_worker_results_empty(self):
        storage = InMemoryWorkflowStorage()
        results = await storage.get_worker_results("nonexistent")
        assert results == []

    async def test_find_similar_exact_match(self):
        storage = InMemoryWorkflowStorage()
        await storage.store_execution(
            _make_execution(exec_id="e1", description="Deploy microservice to staging")
        )
        await storage.store_execution(
            _make_execution(exec_id="e2", description="Run unit tests")
        )

        matches = await storage.find_similar("deploy")
        assert len(matches) == 1
        assert matches[0].id == "e1"

    async def test_find_similar_case_insensitive(self):
        storage = InMemoryWorkflowStorage()
        await storage.store_execution(
            _make_execution(exec_id="e1", description="Deploy Microservice")
        )

        matches = await storage.find_similar("deploy microservice")
        assert len(matches) == 1
        assert matches[0].id == "e1"

    async def test_find_similar_no_match(self):
        storage = InMemoryWorkflowStorage()
        await storage.store_execution(
            _make_execution(exec_id="e1", description="Run tests")
        )

        matches = await storage.find_similar("deploy")
        assert matches == []

    async def test_find_similar_respects_limit(self):
        storage = InMemoryWorkflowStorage()
        for i in range(5):
            await storage.store_execution(
                _make_execution(
                    exec_id=f"e{i}",
                    description=f"Deploy service {i}",
                )
            )

        matches = await storage.find_similar("deploy", limit=3)
        assert len(matches) == 3

    async def test_find_similar_ordered_by_created_at(self):
        storage = InMemoryWorkflowStorage()
        ex_old = WorkflowExecution(
            id="old",
            workflow_name="wf",
            task_description="deploy app",
            total_workers=1,
            total_duration_ms=10.0,
            outcome="completed",
            created_at="2026-01-01T00:00:00+00:00",
        )
        ex_new = WorkflowExecution(
            id="new",
            workflow_name="wf",
            task_description="deploy service",
            total_workers=1,
            total_duration_ms=10.0,
            outcome="completed",
            created_at="2026-06-01T00:00:00+00:00",
        )
        await storage.store_execution(ex_old)
        await storage.store_execution(ex_new)

        matches = await storage.find_similar("deploy")
        assert len(matches) == 2
        assert matches[0].id == "new"
        assert matches[1].id == "old"

    async def test_store_execution_overwrites(self):
        storage = InMemoryWorkflowStorage()
        await storage.store_execution(_make_execution(exec_id="e1", outcome="failed"))
        await storage.store_execution(
            _make_execution(exec_id="e1", outcome="completed")
        )

        fetched = await storage.get_execution("e1")
        assert fetched is not None
        assert fetched.outcome == "completed"


# ═══════════════════════════════════════════════════════════════════════
# SimpleWorkflowEngine
# ═══════════════════════════════════════════════════════════════════════


class TestSimpleWorkflowEngine:
    """Unit tests for the simple workflow engine."""

    async def test_execute_completes_all_phases(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)
        defn = _make_definition()

        result = await engine.execute(defn)

        assert result.status == "completed"
        assert result.phases_completed == ["plan", "execute", "review"]
        assert result.workflow_id == "wf-1"
        assert result.run_id.startswith("run-")
        assert result.duration_ms > 0.0

    async def test_execute_stores_execution(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)
        defn = _make_definition()

        result = await engine.execute(defn)

        execution = await storage.get_execution(result.run_id)
        assert execution is not None
        assert execution.workflow_name == "test-wf"
        assert execution.outcome == "completed"
        assert execution.total_duration_ms > 0.0

    async def test_execute_empty_phases(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)
        defn = _make_definition(phases=[])

        result = await engine.execute(defn)

        assert result.status == "completed"
        assert result.phases_completed == []

    async def test_execute_with_phase_handler(self):
        storage = InMemoryWorkflowStorage()
        call_log: list[str] = []

        async def handler(phase, args, config):
            call_log.append(phase)
            return {"phase": phase, "done": True}

        engine = SimpleWorkflowEngine(storage, phase_handler=handler)
        defn = _make_definition()

        result = await engine.execute(defn)

        assert call_log == ["plan", "execute", "review"]
        assert result.outputs["plan"] == {"phase": "plan", "done": True}
        assert result.outputs["execute"] == {"phase": "execute", "done": True}

    async def test_execute_phase_handler_failure(self):
        storage = InMemoryWorkflowStorage()

        async def failing_handler(phase, args, config):
            if phase == "execute":
                raise RuntimeError("boom")
            return {}

        engine = SimpleWorkflowEngine(storage, phase_handler=failing_handler)
        defn = _make_definition()

        result = await engine.execute(defn)

        assert result.status == "failed"
        assert result.phases_completed == ["plan"]
        assert "execute" not in result.outputs

    async def test_execute_with_args(self):
        storage = InMemoryWorkflowStorage()
        received_args: list = []

        async def handler(phase, args, config):
            received_args.append(args)
            return {}

        engine = SimpleWorkflowEngine(storage, phase_handler=handler)
        defn = _make_definition()

        await engine.execute(defn, args={"key": "value"})

        assert all(a == {"key": "value"} for a in received_args)

    async def test_status_during_execution(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)
        defn = _make_definition()

        result = await engine.execute(defn)

        # After execution, status should reflect completion
        ws = await engine.status(result.run_id)
        assert ws.run_id == result.run_id
        assert ws.progress == 1.0

    async def test_status_not_found(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)

        with pytest.raises(ValueError, match="No execution found"):
            await engine.status("nonexistent-run")

    async def test_resume_completed_execution(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)

        # First, run a workflow to completion
        defn = _make_definition()
        original = await engine.execute(defn)

        # Resume should find the execution and return a result
        resumed = await engine.resume(original.run_id)
        assert resumed.run_id == original.run_id
        assert resumed.status == "completed"

    async def test_resume_not_found(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)

        with pytest.raises(ValueError, match="No execution found"):
            await engine.resume("nonexistent-run")

    async def test_resume_with_worker_results(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)

        # Manually store an execution + some worker results
        ex = _make_execution(exec_id="run-abc", outcome="interrupted")
        await storage.store_execution(ex)
        await storage.store_worker_result(
            "run-abc",
            _make_worker_result(result_id="wr-1", exec_id="run-abc", model="plan"),
        )

        resumed = await engine.resume("run-abc")
        assert resumed.run_id == "run-abc"
        assert resumed.status == "completed"
        assert resumed.phases_completed == ["plan"]

    async def test_multiple_executions(self):
        storage = InMemoryWorkflowStorage()
        engine = SimpleWorkflowEngine(storage)

        defn1 = _make_definition(name="wf-alpha", description="Alpha workflow")
        defn2 = _make_definition(name="wf-beta", description="Beta workflow")

        r1 = await engine.execute(defn1)
        r2 = await engine.execute(defn2)

        assert r1.run_id != r2.run_id

        e1 = await storage.get_execution(r1.run_id)
        e2 = await storage.get_execution(r2.run_id)
        assert e1 is not None
        assert e2 is not None
        assert e1.workflow_name == "wf-alpha"
        assert e2.workflow_name == "wf-beta"


# ═══════════════════════════════════════════════════════════════════════
# Protocol conformance
# ═══════════════════════════════════════════════════════════════════════


class TestProtocolConformance:
    """Verify that implementations satisfy their Protocol contracts."""

    def test_storage_satisfies_protocol(self):
        from loom_ai.contracts_phase2 import WorkflowStorageBackend

        assert isinstance(InMemoryWorkflowStorage(), WorkflowStorageBackend)

    def test_engine_satisfies_protocol(self):
        from loom_ai.contracts_phase2 import WorkflowEngine

        storage = InMemoryWorkflowStorage()
        assert isinstance(SimpleWorkflowEngine(storage), WorkflowEngine)
