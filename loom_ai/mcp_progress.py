"""MCP progress reporter for streaming DemoAgent updates."""

from __future__ import annotations

import json
import sys
import threading


class MCPProgressReporter:
    """Writes MCP ``notifications/progress`` JSON-RPC messages to stdout.

    Uses Content-Length framing matching the MCP stdio transport.
    Thread-safe: multiple calls from background threads are serialized.
    """

    def __init__(self, token: str = "loom-resolve") -> None:
        self._token = token
        self._lock = threading.Lock()

    def report(self, stage: str, message: str, progress_pct: float) -> None:
        body = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {
                "progressToken": self._token,
                "progress": progress_pct,
                "total": 100,
                "message": message,
            },
        })
        encoded = body.encode("utf-8")
        with self._lock:
            sys.stdout.write(
                f"Content-Length: {len(encoded)}\r\n\r\n{body}"
            )
            sys.stdout.flush()
