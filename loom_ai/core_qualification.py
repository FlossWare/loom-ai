"""Executable consumer used to qualify Loom's core agent workflow.

The qualification deliberately uses Loom's public contracts rather than
reaching into private implementation details. It exercises an application-
shaped path:

agent -> MCP-shaped tool -> DAG execution -> verified artifact -> durable
storage -> process boundary -> recovery -> follow-up task.

The initial and recovery phases are separate Python processes. Durable
storage is therefore a hard requirement for the session-boundary gate.
The SQLite backend persists documents only; chunk and embedding data remain
in-process through its MemoryStorageBackend base.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from loom_ai import ExecutionEngine, ExecutionPlan, LoomConfig, Task, ToolDefinition
from loom_ai.backends.agent import InMemoryAgentLoop
from loom_ai.backends.memory_mcp import MemoryToolProvider
from loom_ai.models_agent import AgentOperation
from loom_ai.provenance import EventKind, EvidenceLedger

DOCUMENT_ID = "loom-core-qualification-v1"
ARTIFACT_NAME = "qualified.txt"
FOLLOWUP_NAME = "qualified-followup.txt"
DURABLE_STORAGE = {"sqlite", "postgresql"}
RESULT_MARKER = "__LOOM_QUALIFICATION_RESULT__"


def _require_durable_storage() -> None:
    storage = os.environ.get("LOOM_STORAGE", "sqlite")
    if storage not in DURABLE_STORAGE:
        valid = ", ".join(sorted(DURABLE_STORAGE))
        raise RuntimeError(
            f"Core qualification requires durable LOOM_STORAGE=<{valid}>; "
            "in-memory storage cannot satisfy the process-boundary gate."
        )


async def _run_initial(workspace: Path) -> dict[str, Any]:
    """Run the first half of qualification and persist its evidence."""
    workspace.mkdir(parents=True, exist_ok=True)
    ledger = EvidenceLedger(run_id="core-qualification-initial")
    config = await LoomConfig.from_env()
    _require_durable_storage()
    try:
        tools = MemoryToolProvider()

        async def read_task(path: str) -> str:
            return (workspace / path).read_text(encoding="utf-8")

        tools.register(
            ToolDefinition(
                name="read_task",
                description="Read a qualification fixture from the workspace.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            read_task,
        )

        fixture = workspace / "task.txt"
        fixture.write_text(
            "Loom qualification fixture. Create the verified artifact.\n",
            encoding="utf-8",
        )
        task_description = "Create a verified qualification artifact."
        ledger.record(
            kind=EventKind.TASK_RECEIVED,
            payload={"task": task_description, "fixture": str(fixture)},
        )

        agent = InMemoryAgentLoop(tool_provider=tools)
        agent.register_agent_operation(
            "qualification-agent",
            AgentOperation(
                name="inspect_fixture",
                operation_type="tool_call",
                config={
                    "tool_name": "read_task",
                    "arguments": {"path": fixture.name},
                },
            ),
        )
        turn = await agent.step("qualification-agent")
        investigation_passed = turn.status == "completed"
        if not investigation_passed:
            raise RuntimeError(f"Agent tool turn failed: {turn.output_data}")
        ledger.record(
            kind=EventKind.TOOL_INVOCATION,
            payload={
                "tool": "read_task",
                "turn_id": turn.turn_id,
                "output": turn.output_data,
            },
            verified=True,
        )

        class QualificationRunner:
            async def run(self, task: Task, _config: LoomConfig) -> dict[str, Any]:
                if task.name == "investigate":
                    return {"fixture": fixture.read_text(encoding="utf-8")}
                if task.name == "modify":
                    artifact = workspace / ARTIFACT_NAME
                    artifact.write_text(
                        "Loom core qualification passed.\n",
                        encoding="utf-8",
                    )
                    return {"artifact": str(artifact)}
                raise ValueError(f"Unknown qualification task: {task.name}")

        plan = ExecutionPlan(
            id="core-qualification-plan",
            tasks=[
                Task(
                    id="investigate",
                    name="investigate",
                    description="Inspect fixture.",
                ),
                Task(
                    id="modify",
                    name="modify",
                    description="Create the qualification artifact.",
                    dependencies=["investigate"],
                ),
            ],
        )
        ledger.record(
            kind=EventKind.DECISION,
            payload={
                "decision": "execute investigate then modify through ExecutionEngine"
            },
        )
        plan = await ExecutionEngine(
            config, runner=QualificationRunner()
        ).execute_plan(plan)
        investigation_task = next(
            task for task in plan.tasks if task.id == "investigate"
        )
        modification_task = next(task for task in plan.tasks if task.id == "modify")
        investigation_passed = investigation_passed and (
            investigation_task.status.value == "completed"
        )
        modification_passed = modification_task.status.value == "completed"
        if not investigation_passed or not modification_passed:
            raise RuntimeError("Execution plan did not complete successfully")

        artifact = workspace / ARTIFACT_NAME
        ledger.record(
            kind=EventKind.ARTIFACT_CHANGED,
            payload={"path": str(artifact)},
            verified=True,
        )

        expected = "Loom core qualification passed.\n"
        actual = artifact.read_text(encoding="utf-8") if artifact.exists() else ""
        verified = actual == expected
        ledger.record(
            kind=EventKind.VERIFICATION_RUN,
            payload={
                "path": str(artifact),
                "expected": expected,
                "actual": actual,
                "passed": verified,
            },
            verified=verified,
        )
        if not verified:
            raise RuntimeError("Artifact verification failed")

        evidence = ledger.evidence_chain()
        from loom_ai.models import Document

        document = Document(
            id=DOCUMENT_ID,
            title="Loom core qualification evidence",
            content=(
                "Verified artifact: Loom core qualification passed.\n"
                "Follow-up may rely on this persisted result without replaying the transcript."
            ),
            category="core-qualification",
            metadata={
                "artifact": ARTIFACT_NAME,
                "verification": "passed",
                "run_id": ledger.run_id,
                "evidence_event_ids": [
                    event["event_id"] for event in evidence["events"]
                ],
            },
        )
        stored_id = await config.storage.store_document(document)
        ledger.record(
            kind=EventKind.PERSISTENCE_WRITE,
            payload={
                "backend": type(config.storage).__name__,
                "document_id": stored_id,
            },
            verified=True,
        )

        return {
            "passed": True,
            "phase": "initial",
            "task_submitted": True,
            "task": task_description,
            "investigation_passed": investigation_passed,
            "modification_passed": modification_passed,
            "agent": {"turn_id": turn.turn_id, "status": turn.status},
            "tool": "read_task",
            "tasks": [task.id for task in plan.tasks],
            "artifact": ARTIFACT_NAME,
            "verification": "passed",
            "document_id": stored_id,
            "provenance_event_count": len(ledger.events),
            "provenance_event_kinds": [event.kind.value for event in ledger.events],
        }
    finally:
        await config.close()


async def _run_recovery(workspace: Path) -> dict[str, Any]:
    """Start a fresh process context, recover durable state, and follow up."""
    config = await LoomConfig.from_env()
    _require_durable_storage()
    try:
        document = await config.storage.get_document(DOCUMENT_ID)
        if document is None:
            raise RuntimeError(
                f"Persisted qualification document {DOCUMENT_ID!r} was not recovered"
            )
        if document.metadata.get("verification") != "passed":
            raise RuntimeError("Recovered document lacks verified provenance")
        if "evidence_event_ids" not in document.metadata:
            raise RuntimeError("Recovered document lacks provenance event ids")

        followup = workspace / FOLLOWUP_NAME
        followup.write_text(
            "Follow-up completed from recovered Loom qualification state.\n",
            encoding="utf-8",
        )
        expected = "Follow-up completed from recovered Loom qualification state.\n"
        actual = followup.read_text(encoding="utf-8")
        if actual != expected:
            raise RuntimeError("Follow-up verification failed")

        return {
            "passed": True,
            "phase": "recovery",
            "document_id": document.id,
            "provenance_event_ids": document.metadata["evidence_event_ids"],
            "followup_artifact": FOLLOWUP_NAME,
            "verification": "passed",
        }
    finally:
        await config.close()


def _run_subprocess(phase: str, workspace: Path) -> dict[str, Any]:
    """Execute one qualification phase in a separate interpreter process."""
    command = [
        sys.executable,
        "-m",
        "loom_ai.core_qualification",
        "--phase",
        phase,
        "--workspace",
        str(workspace),
    ]
    env = os.environ.copy()
    env.setdefault("LOOM_STORAGE", "sqlite")
    result = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{phase} phase failed with exit code {result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            try:
                return json.loads(line[len(RESULT_MARKER) :])
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{phase} phase emitted invalid result JSON: {line!r}"
                ) from exc
    raise RuntimeError(
        f"{phase} phase emitted no {RESULT_MARKER} result marker: "
        f"{result.stdout!r}"
    )


def run(workspace: str) -> dict[str, Any]:
    """Run both halves of the process-boundary qualification."""
    root = Path(workspace).resolve()
    initial = _run_subprocess("initial", root)
    recovery = _run_subprocess("recovery", root)
    return {
        "passed": bool(initial.get("passed")) and bool(recovery.get("passed")),
        "initial": initial,
        "recovery": recovery,
        "process_boundary": "separate interpreters",
        "storage": os.environ.get("LOOM_STORAGE", "sqlite"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loom core qualification")
    parser.add_argument(
        "--phase", choices=("initial", "recovery", "all"), default="all"
    )
    parser.add_argument("--workspace", default=os.getcwd())
    args = parser.parse_args()

    try:
        if args.phase == "initial":
            result = asyncio.run(_run_initial(Path(args.workspace).resolve()))
        elif args.phase == "recovery":
            result = asyncio.run(_run_recovery(Path(args.workspace).resolve()))
        else:
            result = run(args.workspace)
    except Exception as exc:
        result = {"passed": False, "phase": args.phase, "error": str(exc)}
    print(f"{RESULT_MARKER}{json.dumps(result, sort_keys=True)}")
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
