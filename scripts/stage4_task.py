#!/usr/bin/env python3
"""Run a deterministic Stage 4 repository task through Loom's HTTP boundary."""
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
        return WorkerResult(self.worker_id, WorkerStatus.SUCCESS, {"path": str(path), "contains_return_41": "return 41" in text}, None, ["inspected repository task file"])


class PlanWorker(Worker):
    worker_id = "plan"

    def execute(self, context: WorkerContext) -> WorkerResult:
        return WorkerResult(self.worker_id, WorkerStatus.SUCCESS, {"replacement": "return 42"}, None, ["planned replacement of return 41 with return 42"])


class ImplementationWorker(Worker):
    worker_id = "implement"

    def execute(self, context: WorkerContext) -> WorkerResult:
        path = pathlib.Path(context.intent.provenance["task_path"])
        text = path.read_text(encoding="utf-8")
        updated = text.replace("return 41", "return 42")
        if updated == text:
            return WorkerResult(self.worker_id, WorkerStatus.FAILURE, error="planned replacement was not present")
        path.write_text(updated, encoding="utf-8")
        return WorkerResult(self.worker_id, WorkerStatus.SUCCESS, {"changed": True}, None, ["implementation applied"])


class VerificationWorker(Worker):
    worker_id = "verify"

    def execute(self, context: WorkerContext) -> WorkerResult:
        path = pathlib.Path(context.intent.provenance["task_path"])
        text = path.read_text(encoding="utf-8")
        accepted = "return 42" in text and "return 41" not in text
        return WorkerResult(self.worker_id, WorkerStatus.SUCCESS if accepted else WorkerStatus.FAILURE, {"acceptance": accepted}, None if accepted else "acceptance condition failed", ["verified repository task result"] if accepted else [])


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: stage4_task.py TASK_PATH")
    task_path = pathlib.Path(sys.argv[1]).resolve()
    intent = Intent(goal="Update the repository task fixture and verify the result", requirements=["inspect", "plan", "implement", "verify"], constraints=["modify only the task file"], acceptance=["the task file contains return 42 and not return 41"], provenance={"task_path": str(task_path)})
    arbiter = Arbiter(workers=[InspectWorker(), PlanWorker(), ImplementationWorker(), VerificationWorker()], max_retries=0)
    server = _LoomHTTPServer(("127.0.0.1", 0), _RequestHandler, arbiter=arbiter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({"goal": intent.goal, "requirements": intent.requirements, "constraints": intent.constraints, "acceptance": intent.acceptance, "provenance": intent.provenance}).encode("utf-8")
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/intents", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            print(json.dumps(json.load(response)))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
