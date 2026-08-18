"""MCP stdio bridge for Claude Code integration.

Translates MCP JSON-RPC over stdin/stdout into loom-ai REST API calls.
Run as ``python -m loom_ai.clients.claude.mcp_bridge`` or reference in
claude_desktop_config.json as an MCP server.

Protocol: JSON-RPC 2.0 over stdin/stdout with Content-Length framing.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_LOOM_URL = os.environ.get(
    "LOOM_URL", "http://127.0.0.1:5000"
).rstrip("/")
_LOOM_KEY = os.environ.get("LOOM_API_KEY", "")

_TOOLS = [
    {
        "name": "loom_search",
        "description": "Search the loom-ai knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "loom_store",
        "description": (
            "Store a document in the loom-ai knowledge base."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "category": {"type": "string", "default": ""},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "loom_consensus",
        "description": "Run multi-model consensus via loom-ai.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt to evaluate",
                },
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Model names to query",
                },
            },
            "required": ["prompt", "models"],
        },
    },
]


def _api_request(
    method: str, path: str, body: dict | None = None
) -> dict:
    url = f"{_LOOM_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "loom-ai-mcp-bridge/1.0",
    }
    if _LOOM_KEY:
        headers["Authorization"] = f"Bearer {_LOOM_KEY}"
    req = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read(4096).decode(errors="replace")
        return {"error": f"HTTP {exc.code}: {body_text}"}
    except urllib.error.URLError as exc:
        return {"error": f"Connection failed: {exc.reason}"}
    except Exception as exc:
        return {"error": str(exc)}


def _handle_tool_call(
    name: str, arguments: dict
) -> list[dict]:
    try:
        if name == "loom_search":
            q = urllib.parse.quote(arguments["query"])
            limit = int(arguments.get("limit", 10))
            result = _api_request(
                "GET", f"/search/text?q={q}&limit={limit}"
            )
        elif name == "loom_store":
            result = _api_request(
                "POST", "/knowledge/documents", {
                    "title": arguments["title"],
                    "content": arguments["content"],
                    "category": arguments.get("category", ""),
                    "metadata": {},
                },
            )
        elif name == "loom_consensus":
            result = _api_request(
                "POST", "/consensus/synthesize", {
                    "prompt": arguments["prompt"],
                    "models": arguments["models"],
                },
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except (KeyError, TypeError) as exc:
        result = {"error": f"Missing required argument: {exc}"}

    return [
        {"type": "text", "text": json.dumps(result, indent=2)}
    ]


def _write_message(data: dict) -> None:
    """Write a JSON-RPC message with Content-Length framing."""
    body = json.dumps(data).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.buffer.write(header.encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_message() -> dict | None:
    """Read a Content-Length–framed JSON-RPC message from stdin."""
    buf = sys.stdin.buffer
    while True:
        header_line = buf.readline()
        if not header_line:
            return None
        header = header_line.decode("utf-8").strip()
        if header.startswith("Content-Length:"):
            length = int(header.split(":", 1)[1].strip())
            while True:
                sep = buf.readline()
                if sep.strip() == b"":
                    break
            body = buf.read(length)
            if not body:
                return None
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
        elif header == "":
            continue


def _respond(
    msg_id: int | str | None, result: dict
) -> None:
    _write_message(
        {"jsonrpc": "2.0", "id": msg_id, "result": result}
    )


def _respond_error(
    msg_id: int | str | None, code: int, message: str
) -> None:
    _write_message({
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    })


def _dispatch(msg: dict) -> bool:
    """Handle one JSON-RPC message. Returns False to stop the loop."""
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        _respond(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "loom-ai",
                "version": "1.0.0",
            },
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        _respond(msg_id, {"tools": _TOOLS})
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        content = _handle_tool_call(tool_name, tool_args)
        _respond(msg_id, {"content": content})
    elif method == "shutdown":
        _respond(msg_id, {})
        return False
    elif msg_id is not None:
        _respond_error(
            msg_id, -32601,
            f"Method not found: {method}",
        )
    return True


def main() -> None:
    while True:
        msg = _read_message()
        if msg is None or not _dispatch(msg):
            break


if __name__ == "__main__":
    main()
