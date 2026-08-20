"""Unified MCP server exposing all loom-ai protocols as tools.

Translates MCP JSON-RPC over stdin/stdout into loom-ai REST API calls.
Covers all protocol backends: LLM, storage, queue, secrets, search,
graph, embedding, consensus, tools, resources, and router.

Usage::

    python -m loom_ai.mcp_server

    # Or in claude_desktop_config.json / MCP client config:
    {"command": "python", "args": ["-m", "loom_ai.mcp_server"]}

Environment:
    LOOM_URL      Base URL of loom-ai server (default: http://127.0.0.1:5000)
    LOOM_API_KEY  Optional bearer token for authenticated servers
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
_MAX_MESSAGE_SIZE = 10 * 1024 * 1024


def _str_prop(desc: str) -> dict:
    return {"type": "string", "description": desc}


def _int_prop(desc: str, default: int | None = None) -> dict:
    d: dict = {"type": "integer", "description": desc}
    if default is not None:
        d["default"] = default
    return d


def _float_prop(desc: str, default: float | None = None) -> dict:
    d: dict = {"type": "number", "description": desc}
    if default is not None:
        d["default"] = default
    return d


_TOOLS: list[dict] = [
    {
        "name": "loom_chat",
        "description": "Send chat completion via loom-ai LLM backend",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": _str_prop("Role"),
                            "content": _str_prop("Content"),
                        },
                    },
                    "description": "Chat messages",
                },
                "model": _str_prop("Model name"),
                "temperature": _float_prop("Temperature", 0.7),
                "max_tokens": _int_prop("Max tokens"),
            },
            "required": ["messages"],
        },
    },
    {
        "name": "loom_list_models",
        "description": "List available LLM models",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "loom_search",
        "description": "Full-text search the knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": _str_prop("Search query"),
                "limit": _int_prop("Max results", 10),
            },
            "required": ["query"],
        },
    },
    {
        "name": "loom_store",
        "description": "Store a document in the knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": _str_prop("Document title"),
                "content": _str_prop("Document content"),
                "category": _str_prop("Category"),
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "loom_consensus",
        "description": "Run multi-model consensus",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": _str_prop("Prompt to evaluate"),
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Model names to query",
                },
            },
            "required": ["prompt", "models"],
        },
    },
    {
        "name": "loom_synthesize",
        "description": "Multi-model synthesis with arbiter",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": _str_prop("Prompt"),
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "arbiter_model": _str_prop("Arbiter model"),
            },
            "required": ["prompt", "models"],
        },
    },
    {
        "name": "loom_queue_enqueue",
        "description": "Add items to a named queue",
        "inputSchema": {
            "type": "object",
            "properties": {
                "queue_name": _str_prop("Queue name"),
                "payload": {
                    "type": "object",
                    "description": "Item payload",
                },
            },
            "required": ["queue_name", "payload"],
        },
    },
    {
        "name": "loom_queue_status",
        "description": "Get queue status counts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "queue_name": _str_prop("Queue name"),
            },
            "required": ["queue_name"],
        },
    },
    {
        "name": "loom_secret_list",
        "description": "List secret names (no values)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "loom_secret_get",
        "description": "Retrieve a secret value",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": _str_prop("Secret name"),
                "reason": _str_prop("Access reason (required)"),
            },
            "required": ["name", "reason"],
        },
    },
    {
        "name": "loom_graph_add_node",
        "description": "Add a node to the knowledge graph",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": _str_prop("Node label"),
                "properties": {
                    "type": "object",
                    "description": "Node properties",
                },
            },
            "required": ["label"],
        },
    },
    {
        "name": "loom_graph_neighbors",
        "description": "Get neighbors of a graph node",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": _str_prop("Node ID"),
                "edge_label": _str_prop("Filter by edge label"),
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "loom_router_select",
        "description": "Select a model via Thompson Sampling router",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": _str_prop("Task type"),
            },
            "required": ["task_type"],
        },
    },
    {
        "name": "loom_router_stats",
        "description": "Get router performance statistics",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "loom_health",
        "description": "Check loom-ai server health",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class _ToolError(Exception):
    """Transport or tool-execution error."""


def _api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{_LOOM_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "loom-ai-mcp-server/1.0",
    }
    if _LOOM_KEY:
        headers["Authorization"] = f"Bearer {_LOOM_KEY}"
    req = urllib.request.Request(
        url, data=data, headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        text = exc.read(4096).decode(errors="replace")
        raise _ToolError(f"HTTP {exc.code}: {text}") from exc
    except urllib.error.URLError as exc:
        raise _ToolError(f"Connection failed: {exc.reason}") from exc
    except Exception as exc:
        raise _ToolError(str(exc)) from exc


def _handle(name: str, args: dict) -> dict:
    """Execute a tool call and return MCP result."""
    try:
        result = _dispatch(name, args)
        text = json.dumps(result, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}]}
    except _ToolError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        }


def _dispatch_secret_get(args: dict) -> dict:
    sn = urllib.parse.quote(args["name"])
    hdrs = {
        "Content-Type": "application/json",
        "User-Agent": "loom-ai-mcp-server/1.0",
        "X-Secret-Access-Reason": args["reason"],
    }
    if _LOOM_KEY:
        hdrs["Authorization"] = f"Bearer {_LOOM_KEY}"
    req = urllib.request.Request(
        f"{_LOOM_URL}/secrets/{sn}/reveal",
        data=None, headers=hdrs, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        text = exc.read(4096).decode(errors="replace")
        raise _ToolError(f"HTTP {exc.code}: {text}") from exc


def _dispatch_search(args: dict) -> dict:
    q = urllib.parse.quote(args["query"])
    limit = int(args.get("limit", 10))
    return _api("GET", f"/search/text?q={q}&limit={limit}")


def _dispatch_graph_neighbors(args: dict) -> dict:
    nid = urllib.parse.quote(args["node_id"])
    edge = args.get("edge_label", "")
    qs = f"?edge_label={edge}" if edge else ""
    return _api("GET", f"/graph/nodes/{nid}/neighbors{qs}")


_DISPATCH_TABLE = {
    "loom_chat": lambda a: _api("POST", "/llm/chat", {
        "messages": a["messages"], "model": a.get("model"),
        "temperature": a.get("temperature", 0.7),
        "max_tokens": a.get("max_tokens"),
    }),
    "loom_list_models": lambda a: _api("GET", "/llm/models"),
    "loom_search": _dispatch_search,
    "loom_store": lambda a: _api("POST", "/knowledge/documents", {
        "title": a["title"], "content": a["content"],
        "category": a.get("category", ""),
    }),
    "loom_consensus": lambda a: _api("POST", "/consensus/gather", {
        "messages": [{"role": "user", "content": a["prompt"]}],
        "models": a["models"],
    }),
    "loom_synthesize": lambda a: _api("POST", "/consensus/synthesize", {
        "prompt": a["prompt"], "models": a["models"],
        "arbiter_model": a.get("arbiter_model"),
    }),
    "loom_queue_enqueue": lambda a: _api(
        "POST",
        f"/pipeline/queues/{a['queue_name']}/enqueue",
        {"items": [{"payload": a["payload"]}]},
    ),
    "loom_queue_status": lambda a: _api(
        "GET",
        f"/pipeline/queues/{urllib.parse.quote(a['queue_name'])}/status",
    ),
    "loom_secret_list": lambda a: _api("GET", "/secrets/"),
    "loom_secret_get": _dispatch_secret_get,
    "loom_graph_add_node": lambda a: _api("POST", "/graph/nodes", {
        "label": a["label"],
        "properties": a.get("properties", {}),
    }),
    "loom_graph_neighbors": _dispatch_graph_neighbors,
    "loom_router_select": lambda a: _api("POST", "/router/select", {
        "task_type": a["task_type"],
    }),
    "loom_router_stats": lambda a: _api("GET", "/router/performance"),
    "loom_health": lambda a: _api("GET", "/health"),
}


def _dispatch(name: str, args: dict) -> dict:
    handler = _DISPATCH_TABLE.get(name)
    if handler is None:
        raise _ToolError(f"Unknown tool: {name}")
    return handler(args)


def _read_message() -> dict | None:
    """Read a JSON-RPC message with Content-Length framing."""
    content_length = -1
    while True:
        header = sys.stdin.readline()
        if not header or header.strip() == "":
            break
        if header.lower().startswith("content-length:"):
            content_length = int(header.split(":", 1)[1].strip())
    if content_length <= 0:
        return None
    if content_length > _MAX_MESSAGE_SIZE:
        return None
    raw = sys.stdin.read(content_length)
    return json.loads(raw)


def _write_message(msg: dict) -> None:
    """Write a JSON-RPC message with Content-Length framing."""
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def _respond(req_id: int | str | None, result: dict) -> None:
    _write_message({"jsonrpc": "2.0", "id": req_id, "result": result})


def _negotiate_version(
    client_version: str | None,
) -> str:
    if client_version in _SUPPORTED_VERSIONS:
        return client_version
    return _LATEST_VERSION


def main() -> None:
    """Run the MCP server loop over stdin/stdout."""
    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr,
    )
    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            version = _negotiate_version(
                params.get("protocolVersion"),
            )
            _respond(req_id, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "loom-ai",
                    "version": "1.0.0",
                },
            })
        elif method == "notifications/initialized":
            logger.debug("Client initialized")
        elif method == "tools/list":
            _respond(req_id, {"tools": _TOOLS})
        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            _respond(req_id, _handle(name, arguments))
        elif method == "ping":
            _respond(req_id, {})
        else:
            _write_message({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            })


if __name__ == "__main__":
    main()
