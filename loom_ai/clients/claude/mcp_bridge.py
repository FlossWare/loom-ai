"""MCP stdio bridge for Claude Code integration.

Translates MCP JSON-RPC over stdin/stdout into loom-ai REST API calls.
Run as ``python -m loom_ai.clients.claude.mcp_bridge`` or reference in
claude_desktop_config.json as an MCP server.

Protocol: JSON-RPC 2.0 over stdin/stdout with Content-Length framing.

Supported MCP protocol versions (negotiation via ``initialize``)::

    - 2024-11-05 (legacy)
    - 2025-03-26 (current family)

Unsupported client versions receive a JSON-RPC error; the bridge stays up.
Malformed Content-Length / JSON produce protocol errors, not silent EOF.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_LOOM_URL = os.environ.get("LOOM_URL", "http://127.0.0.1:5000").rstrip("/")
_LOOM_KEY = os.environ.get("LOOM_API_KEY", "")

_SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-03-26",
    "2024-11-05",
)
_DEFAULT_PROTOCOL_VERSION = "2024-11-05"
_MAX_CONTENT_LENGTH = 4 * 1024 * 1024
_MAX_SEARCH_LIMIT = 100

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

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
        "description": "Store a document in the loom-ai knowledge base.",
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


def _api_request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{_LOOM_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _LOOM_KEY:
        headers["Authorization"] = f"Bearer {_LOOM_KEY}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"connection failed: {exc.reason}") from exc


def _require_str(args: dict, key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"missing or invalid '{key}'")
    return val


def _clamp_limit(raw: Any) -> int:
    try:
        limit = int(raw) if raw is not None else 10
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return min(limit, _MAX_SEARCH_LIMIT)


def _handle_tool_call(name: str, arguments: dict) -> list[dict]:
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")

    if name == "loom_search":
        query = _require_str(arguments, "query")
        limit = _clamp_limit(arguments.get("limit", 10))
        result = _api_request(
            "GET",
            f"/search/text?q={urllib.parse.quote(query)}&limit={limit}",
        )
        text = json.dumps(result, indent=2)
    elif name == "loom_store":
        title = _require_str(arguments, "title")
        content = _require_str(arguments, "content")
        category = arguments.get("category", "")
        if category is not None and not isinstance(category, str):
            raise ValueError("category must be a string")
        result = _api_request(
            "POST",
            "/knowledge/documents",
            {
                "title": title,
                "content": content,
                "category": category or "",
            },
        )
        text = json.dumps(result, indent=2)
    elif name == "loom_consensus":
        prompt = _require_str(arguments, "prompt")
        models = arguments.get("models")
        if not isinstance(models, list) or not models:
            raise ValueError("models must be a non-empty array of strings")
        if not all(isinstance(m, str) and m for m in models):
            raise ValueError("models must be a non-empty array of strings")
        result = _api_request(
            "POST",
            "/consensus/synthesize",
            {"prompt": prompt, "models": models},
        )
        text = json.dumps(result, indent=2)
    else:
        raise ValueError(f"unknown tool: {name}")

    return [{"type": "text", "text": text}]


def _write_message(msg: dict) -> None:
    body = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _respond(msg_id: int | str | None, result: dict) -> None:
    _write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _respond_error(
    msg_id: int | str | None,
    code: int,
    message: str,
) -> None:
    _write_message(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }
    )


class _FramingError(Exception):
    """Content-Length framing problem (recoverable protocol error)."""


class _ParseError(Exception):
    """Body was not valid JSON."""


def _read_message() -> dict | None:
    """Read a Content-Length–framed JSON-RPC message from stdin.

    Returns None on clean EOF. Raises ``_FramingError`` / ``_ParseError``
    for recoverable protocol problems so the main loop can emit errors.
    """
    buf = sys.stdin.buffer
    length: int | None = None
    while True:
        header_line = buf.readline()
        if not header_line:
            if length is None:
                return None
            raise _FramingError("EOF while reading headers")
        header = header_line.decode("utf-8", errors="replace").strip()
        if not header:
            break
        lower = header.lower()
        if lower.startswith("content-length:"):
            try:
                length = int(header.split(":", 1)[1].strip())
            except ValueError as exc:
                raise _FramingError(
                    f"invalid Content-Length: {header!r}"
                ) from exc
            if length < 0 or length > _MAX_CONTENT_LENGTH:
                raise _FramingError(
                    f"Content-Length out of range: {length}"
                )

    if length is None:
        return _read_message()

    body = buf.read(length)
    if len(body) < length:
        raise _FramingError("truncated body")
    try:
        msg = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _ParseError(str(exc)) from exc
    if not isinstance(msg, dict):
        raise _ParseError("JSON-RPC message must be an object")
    return msg


def _negotiate_protocol(params: dict) -> str:
    requested = params.get("protocolVersion") or params.get("protocol_version")
    if requested is None:
        return _DEFAULT_PROTOCOL_VERSION
    if not isinstance(requested, str):
        raise ValueError("protocolVersion must be a string")
    if requested in _SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    raise ValueError(
        f"unsupported protocol version {requested!r}; "
        f"supported: {', '.join(_SUPPORTED_PROTOCOL_VERSIONS)}"
    )


def _dispatch(msg: dict) -> bool:
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if method == "initialize":
        try:
            version = _negotiate_protocol(params)
        except ValueError as exc:
            _respond_error(msg_id, _INVALID_PARAMS, str(exc))
            return True
        _respond(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "loom-ai", "version": "1.0.0"},
            },
        )
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        _respond(msg_id, {"tools": _TOOLS})
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        if not isinstance(tool_name, str) or not tool_name:
            _respond_error(msg_id, _INVALID_PARAMS, "tool name required")
            return True
        try:
            content = _handle_tool_call(
                tool_name, tool_args if isinstance(tool_args, dict) else {}
            )
            _respond(msg_id, {"content": content})
        except ValueError as exc:
            _respond_error(msg_id, _INVALID_PARAMS, str(exc))
        except RuntimeError as exc:
            _respond_error(msg_id, _INTERNAL_ERROR, str(exc))
        except Exception as exc:
            logger.exception("tool call failed")
            _respond_error(msg_id, _INTERNAL_ERROR, type(exc).__name__)
    elif method == "shutdown":
        _respond(msg_id, {})
        return False
    elif method == "ping":
        _respond(msg_id, {})
    elif msg_id is not None:
        _respond_error(msg_id, _METHOD_NOT_FOUND, f"Method not found: {method}")
    return True


def main() -> None:
    while True:
        try:
            msg = _read_message()
        except _FramingError as exc:
            _respond_error(None, _INVALID_REQUEST, str(exc))
            continue
        except _ParseError as exc:
            _respond_error(None, _PARSE_ERROR, f"Parse error: {exc}")
            continue
        if msg is None:
            break
        if not _dispatch(msg):
            break


if __name__ == "__main__":
    main()
