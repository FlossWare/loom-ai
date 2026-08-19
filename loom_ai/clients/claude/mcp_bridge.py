"""MCP stdio bridge for Claude Code integration.

Translates MCP JSON-RPC over stdin/stdout into loom-ai REST API calls.
Run as ``python -m loom_ai.clients.claude.mcp_bridge`` or reference in
claude_desktop_config.json as an MCP server.

Protocol: JSON-RPC 2.0 over stdin/stdout with Content-Length framing.

Supported MCP protocol versions: 2024-11-05, 2025-03-26.
The server negotiates by echoing the client's version if supported,
otherwise falling back to the latest supported version.
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

_SUPPORTED_VERSIONS = ["2024-11-05", "2025-03-26"]
_LATEST_VERSION = _SUPPORTED_VERSIONS[-1]

_LOOM_URL = os.environ.get("LOOM_URL", "http://127.0.0.1:5000").rstrip("/")
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
        "description": ("Store a document in the loom-ai knowledge base."),
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

_MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB

_TYPE_CHECKS: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class _ToolError(Exception):
    """Transport or tool-execution error (distinct from successful results)."""


def _api_request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{_LOOM_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "loom-ai-mcp-bridge/1.0",
    }
    if _LOOM_KEY:
        headers["Authorization"] = f"Bearer {_LOOM_KEY}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read(4096).decode(errors="replace")
        raise _ToolError(f"HTTP {exc.code}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise _ToolError(f"Connection failed: {exc.reason}") from exc
    except Exception as exc:
        raise _ToolError(str(exc)) from exc


def _validate_arguments(name: str, arguments: dict) -> None:
    """Validate tool arguments against the schema in _TOOLS."""
    if not isinstance(arguments, dict):
        raise _ToolError("Arguments must be a key-value object")

    tool_def = next((t for t in _TOOLS if t["name"] == name), None)
    if tool_def is None:
        raise _ToolError(f"Unknown tool: {name}")

    schema = tool_def.get("inputSchema", {})
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    for req_field in required:
        if req_field not in arguments:
            raise _ToolError(f"Missing required argument: {req_field}")
    for arg_name, arg_value in arguments.items():
        if arg_name not in properties:
            continue
        expected_type = properties[arg_name].get("type")
        if expected_type in _TYPE_CHECKS:
            if not isinstance(arg_value, _TYPE_CHECKS[expected_type]):
                raise _ToolError(f"Argument '{arg_name}' must be {expected_type}")


def _handle_tool_call(name: str, arguments: dict) -> dict:
    """Execute a tool call. Returns MCP-format result dict with content list."""
    try:
        _validate_arguments(name, arguments)

        if name == "loom_search":
            q = urllib.parse.quote(arguments["query"])
            limit = int(arguments.get("limit", 10))
            result = _api_request("GET", f"/search/text?q={q}&limit={limit}")
        elif name == "loom_store":
            result = _api_request(
                "POST",
                "/knowledge/documents",
                {
                    "title": arguments["title"],
                    "content": arguments["content"],
                    "category": arguments.get("category", ""),
                    "metadata": {},
                },
            )
        elif name == "loom_consensus":
            result = _api_request(
                "POST",
                "/consensus/synthesize",
                {
                    "prompt": arguments["prompt"],
                    "models": arguments["models"],
                },
            )
        else:
            raise _ToolError(f"Unknown tool: {name}")

        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        }
    except _ToolError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        }


def _write_message(data: dict) -> None:
    """Write a JSON-RPC message with Content-Length framing."""
    body = json.dumps(data).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.buffer.write(header.encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


_PARSE_ERROR = "parse_error"


def _parse_content_length(header: str) -> int:
    """Extract and validate Content-Length value. Raises ValueError on bad input."""
    length = int(header.split(":", 1)[1].strip())
    if length <= 0:
        raise ValueError("must be positive")
    if length > _MAX_MESSAGE_SIZE:
        raise ValueError("exceeds maximum message size")
    return length


def _read_framed_body(buf, length: int) -> dict | str:
    """Read and parse a JSON body of exactly *length* bytes."""
    while True:
        sep = buf.readline()
        if sep.strip() == b"":
            break
    body = buf.read(length)
    if len(body) < length:
        _respond_error(
            None, -32700,
            f"Parse error: expected {length} bytes, got {len(body)}",
        )
        return _PARSE_ERROR
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        _respond_error(None, -32700, f"Parse error: {exc.msg}")
        return _PARSE_ERROR


def _read_message() -> dict | str | None:
    """Read a Content-Length-framed JSON-RPC message from stdin.

    Returns the parsed dict, None on EOF, or _PARSE_ERROR after sending
    a JSON-RPC error response (the caller should skip and read again).
    """
    buf = sys.stdin.buffer
    while True:
        header_line = buf.readline()
        if not header_line:
            return None
        header = header_line.decode("utf-8").strip()
        if not header:
            continue
        if not header.startswith("Content-Length:"):
            continue
        try:
            length = _parse_content_length(header)
        except (ValueError, IndexError):
            _respond_error(
                None, -32700,
                f"Parse error: invalid Content-Length in '{header}'",
            )
            return _PARSE_ERROR
        return _read_framed_body(buf, length)


def _respond(msg_id: int | str | None, result: dict) -> None:
    _write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _respond_error(msg_id: int | str | None, code: int, message: str) -> None:
    _write_message(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }
    )


def _on_initialize(msg_id, params):
    client_version = params.get("protocolVersion")
    supported = client_version in _SUPPORTED_VERSIONS
    negotiated = client_version if supported else _LATEST_VERSION
    if client_version and not supported:
        logger.warning(
            "Unsupported protocol version '%s', falling back to '%s'",
            client_version, _LATEST_VERSION,
        )
    _respond(msg_id, {
        "protocolVersion": negotiated,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "loom-ai", "version": "1.0.0"},
    })


def _on_tools_call(msg_id, params):
    tool_name = params.get("name", "")
    tool_args = params.get("arguments", {})
    result = _handle_tool_call(tool_name, tool_args)
    _respond(msg_id, result)


_METHOD_HANDLERS = {
    "initialize": _on_initialize,
    "notifications/initialized": lambda _id, _p: None,
    "tools/list": lambda msg_id, _p: _respond(msg_id, {"tools": _TOOLS}),
    "tools/call": _on_tools_call,
}


def _dispatch(msg: dict) -> bool:
    """Handle one JSON-RPC message. Returns False to stop the loop."""
    msg_id = msg.get("id")

    if "method" not in msg:
        _respond_error(msg_id, -32600, "Invalid Request: missing 'method'")
        return True

    method = msg["method"]
    if method == "shutdown":
        _respond(msg_id, {})
        return False

    handler = _METHOD_HANDLERS.get(method)
    if handler is not None:
        handler(msg_id, msg.get("params", {}))
    elif msg_id is not None:
        _respond_error(msg_id, -32601, f"Method not found: {method}")
    return True


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
        stream=sys.stderr,
    )
    while True:
        msg = _read_message()
        if msg is None:
            break
        if msg is _PARSE_ERROR:
            continue
        if not _dispatch(msg):
            break


if __name__ == "__main__":
    main()
