#!/usr/bin/env python3
"""Run the deterministic Stage 4 repository-task through Loom's HTTP boundary."""
from __future__ import annotations

import json
import pathlib
import sys
import threading
import urllib.request

from loom_ai import Arbiter, Intent, Worker, WorkerContext, WorkerResult, WorkerStatus
from loom_ai.server import _LoomHTTPServer, _RequestHandler


class InspectWorker(Worker):
    worker_id = "inspect"

    def execute(self, context: WorkerContext) -> WorkerResult:
        path = pathlib.Path(context.intent.provenance["task_path"])
        text = path.read_text(encoding="utf-8")
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"path": str(path), "contains_return_41": "return 41" in text},
            evidence=["inspected repository task file"],
        )


class PlanWorker(Worker):
    worker_id = "plan"

    def execute(self, context: WorkerContext) -> WorkerResult:
        inspect = next(e for e in context.evidence if e.get("worker_id") == "inspect")
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"replacement": "return 42"},
            evidence=[{"plan": "replace return 41 with return 42", "inspection": inspect}],
        )


class ImplementationWorker(Worker):
    worker_id = "implement"

    def execute(self, context: WorkerContext) -> WorkerResult:
        path = pathlib.Path(context.intent.provenance["task_path"])
        text = path.read_text(encoding="utf-8")
        updated = text.replace("return 41", "return 42")
        if updated == text:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILURE,
                error="planned replacement was not present",
            )
        path.write_text(updated, encoding="utf-8")
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"changed": True},
            evidence=["implementation applied"],
        )


class VerificationWorker(Worker):
    worker_id = "verify"

    def execute(self, context: WorkerContext) -> WorkerResult:
        path = pathlib.Path(context.intent.provenance["task_path"])
        text = path.read_text(encoding="utf-8")
        accepted = "return 42" in text and "return 41" not in text
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS if accepted else WorkerStatus.FAILURE,
            output={"acceptance": accepted},
            evidence=["verified repository task result"] if accepted else [],
            error=None if accepted else "acceptance condition failed",
        )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: stage4_task.py TASK_PATH")

    task_path = pathlib.Path(sys.argv[1]).resolve()
    intent = Intent(
        goal="Update the repository task fixture and verify the result",
        requirements=["inspect", "plan", "implement", "verify"],
        constraints=["modify only the task file"],
        acceptance=["the task file contains return 42 and not return 41"],
        provenance={"task_path": str(task_path)},
    )

    arbiter = Arbiter(
        workers=[InspectWorker(), PlanWorker(), ImplementationWorker(), VerificationWorker()],
        max_retries=0,
    )
    server = _LoomHTTPServer(("127.0.0.1", 0), _RequestHandler, arbiter=arbiter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/intents",
            data=json.dumps(intent.to_dict()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
        print(json.dumps(payload))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
