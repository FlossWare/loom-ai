"""MCP progress reporter for streaming DemoAgent updates."""

from __future__ import annotations

import json
import sys


class MCPProgressReporter:
    """Writes MCP ``notifications/progress`` JSON-RPC messages to stdout.

    Uses Content-Length framing matching the MCP stdio transport.
    Thread-safe: shares ``_MCP_STDOUT_LOCK`` with the MCP server to
    prevent interleaved JSON-RPC writes on stdout.
    """

    def __init__(self, token: str = "loom-resolve") -> None:
        self._token = token

    def report(self, stage: str, message: str, progress_pct: float) -> None:
        from loom_ai.mcp_server import _MCP_STDOUT_LOCK

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": self._token,
                    "progress": progress_pct,
                    "total": 100,
                    "message": message,
                },
            }
        )
        encoded = body.encode("utf-8")
        with _MCP_STDOUT_LOCK:
            sys.stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n{body}")
            sys.stdout.flush()
