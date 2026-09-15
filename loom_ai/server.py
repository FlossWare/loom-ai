"""Minimal HTTP transport for the Loom execution substrate.

The server owns transport and request-to-Intent translation. Execution remains
owned by the supplied Arbiter and its Workers. Provider/model access is
deliberately not part of this module.
"""

from __future__ import annotations

import argparse
import json
import socketserver
from dataclasses import asdict, is_dataclass
from enum import Enum
from http import HTTPStatus
from typing import Any
from uuid import uuid4

from loom_ai.arbiter import Arbiter
from loom_ai.intent import Intent
from loom_ai.worker import WorkerContext, WorkerResult, WorkerStatus

MAX_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB limit for incoming requests


class _TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class LoomServer:
    """HTTP transport boundary for a configured Loom Arbiter."""

    def __init__(
        self, arbiter: Arbiter, *, host: str = "localhost", port: int = 8000
    ) -> None:
        self.host = host
        self.port = port
        self.arbiter = arbiter

    def execute(self, intent: Intent) -> WorkerResult:
        """Execute an Intent through the configured Arbiter."""
        return self.arbiter.execute(WorkerContext(intent=intent))

    def serve_forever(self) -> None:
        """Serve requests until interrupted."""
        handler = self._handler_factory()
        server = _TCPServer((self.host, self.port), handler)
        self.port = server.server_address[1]
        server.serve_forever()

    def _handler_factory(self) -> type[socketserver.StreamRequestHandler]:
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, default=_json_default).encode("utf-8")
                reason = status.phrase
                header = (
                    f"HTTP/1.1 {status.value} {reason}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                )
                self.wfile.write(header.encode("utf-8") + body)

            def handle(self) -> None:
                request_line = self.rfile.readline(65536).decode("utf-8", "replace")
                if not request_line:
                    return
                parts = request_line.split()
                if len(parts) < 2:
                    return
                method, path = parts[0], parts[1]

                headers = {}
                while True:
                    line = self.rfile.readline(65536).decode("utf-8", "replace")
                    if not line or line in ("\r\n", "\n"):
                        break
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip().lower()] = v.strip()

                if method == "GET":
                    if path == "/health":
                        self._send(HTTPStatus.OK, {"status": "ok"})
                        return
                    self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return

                if method == "POST":
                    if path != "/intents":
                        self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return

                    try:
                        length = int(headers.get("content-length", "0"))
                        if length > MAX_PAYLOAD_BYTES:
                            self._send(
                                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                {"error": "payload too large"},
                            )
                            return

                        raw_body = self.rfile.read(length)
                        payload = json.loads(raw_body.decode("utf-8"))
                        goal = payload["goal"]
                        intent = Intent(
                            title=payload.get("title", "Intent"),
                            goal=goal,
                            requirements=tuple(payload.get("requirements", ())),
                            constraints=tuple(payload.get("constraints", ())),
                            acceptance=tuple(payload.get("acceptance", ())),
                            intent_id=payload.get("intent_id") or str(uuid4()),
                        )
                        result = owner.execute(intent)
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                        return
                    except Exception as exc:  # pragma: no cover - transport safety net
                        self._send(
                            HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)}
                        )
                        return

                    self._send(HTTPStatus.OK, _result_payload(result))
                    return

                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        return Handler


def _result_payload(result: WorkerResult) -> dict[str, Any]:
    return {
        "worker_id": result.worker_id,
        "status": result.status.value,
        "output": result.output,
        "evidence": result.evidence,
        "error": result.error,
        "metadata": result.metadata,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    """Run a transport-only server for manual health checks."""
    parser = argparse.ArgumentParser(description="Run the Loom HTTP server")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    class NoOpWorker:
        worker_id = "server"

        def execute(self, context: WorkerContext) -> WorkerResult:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.SUCCESS,
                output={"intent_id": context.intent.intent_id},
            )

    def evaluate(result: WorkerResult, _context: WorkerContext):
        from loom_ai.arbiter import ArbiterDecision, WorkerEvaluation

        if result.successful:
            return WorkerEvaluation(
                ArbiterDecision.COMPLETE, reason="transport smoke test"
            )
        return WorkerEvaluation(
            ArbiterDecision.COMPLETE, reason=result.error or "failed"
        )

    arbiter = Arbiter([NoOpWorker()], evaluate)
    LoomServer(arbiter, host=args.host, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
