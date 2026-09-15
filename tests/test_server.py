"""Tests for the Loom HTTP transport boundary."""

from __future__ import annotations

import json
from threading import Thread
from urllib.request import Request, urlopen

from loom_ai.server import LoomServer
from loom_ai.worker import WorkerContext, WorkerResult, WorkerStatus


class RecordingWorker:
    worker_id = "recording"

    def execute(self, context: WorkerContext) -> WorkerResult:
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"goal": context.intent.goal},
            evidence=({"source": self.worker_id},),
        )


def test_server_executes_intent_over_http() -> None:
    server = LoomServer([RecordingWorker()], port=0)
    httpd = server._handler_factory()
    from http.server import ThreadingHTTPServer

    instance = ThreadingHTTPServer((server.host, server.port), httpd)
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.host}:{instance.server_port}"
        with urlopen(f"{base_url}/health") as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}

        request = Request(
            f"{base_url}/intents",
            data=json.dumps({"title": "Test", "goal": "exercise Loom"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            payload = json.load(response)

        assert payload["status"] == "success"
        assert payload["output"][0]["output"] == {"goal": "exercise Loom"}
        assert payload["output"][0]["worker_id"] == "recording"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def test_server_rejects_intent_without_goal() -> None:
    server = LoomServer([RecordingWorker()], port=0)
    from http.server import ThreadingHTTPServer

    instance = ThreadingHTTPServer((server.host, server.port), server._handler_factory())
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://{server.host}:{instance.server_port}/intents",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(request)
            raise AssertionError("expected HTTP 400")
        except Exception as exc:
            assert getattr(exc, "code", None) == 400
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)
