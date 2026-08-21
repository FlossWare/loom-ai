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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _AsyncTask:
    task_id: str
    status: str
    progress: str
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: float = 0.0
    cancelled: bool = False
    timeout: float = 300.0
    progress_token: str = ""


_ASYNC_TASKS: dict[str, _AsyncTask] = {}
_ASYNC_LOCK = threading.Lock()
_MAX_ASYNC_TASKS = 100
_TASK_TTL_SECONDS = 3600
_MCP_STDOUT_LOCK = threading.Lock()

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
        "name": "loom_graph_add_entity",
        "description": "Add an entity to the knowledge graph",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": _str_prop("Entity label"),
                "entity_type": _str_prop("Entity type"),
                "properties": {
                    "type": "object",
                    "description": "Entity properties",
                },
            },
            "required": ["label", "entity_type"],
        },
    },
    {
        "name": "loom_graph_relationships",
        "description": "Get relationships of a knowledge graph entity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": _str_prop("Entity ID"),
                "relation_type": _str_prop("Filter by relation type"),
            },
            "required": ["entity_id"],
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
    {
        "name": "loom_resolve_issue",
        "description": "Resolve a GitHub issue end-to-end using the DemoAgent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_number": _int_prop("GitHub issue number"),
                "workspace": _str_prop("Repo workspace path"),
                "issue_text": _str_prop("Issue description text"),
            },
            "required": ["issue_number"],
        },
    },
    {
        "name": "loom_resolve_issue_async",
        "description": (
            "Start issue resolution in the background and return a task_id "
            "immediately. Poll with loom_resolve_issue_status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_number": _int_prop("GitHub issue number"),
                "workspace": _str_prop("Repo workspace path"),
                "issue_text": _str_prop("Issue description text"),
                "timeout": _int_prop("Max execution time in seconds", 300),
                "progress_token": _str_prop("MCP progress token for notifications"),
            },
            "required": ["issue_number"],
        },
    },
    {
        "name": "loom_resolve_issue_status",
        "description": "Poll status of an async issue resolution task by task_id",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": _str_prop("Task ID from loom_resolve_issue_async"),
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "loom_resolve_issue_cancel",
        "description": "Cancel a running async issue resolution task",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": _str_prop("Task ID to cancel"),
            },
            "required": ["task_id"],
        },
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
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310  # NOSONAR — URL from LOOM_BASE_URL env var, not user input
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
        data=None,
        headers=hdrs,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # NOSONAR — URL from LOOM_BASE_URL env var, not user input
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        text = exc.read(4096).decode(errors="replace")
        raise _ToolError(f"HTTP {exc.code}: {text}") from exc


def _dispatch_resolve_issue(args: dict) -> dict:
    import asyncio as _asyncio

    from loom_ai.backends.code_actions import validate_workspace
    from loom_ai.demo_agent import DemoAgent

    async def _run() -> dict:
        workspace_path = args.get("workspace", os.getcwd())
        workspace = validate_workspace(workspace_path)
        agent = await DemoAgent.create(workspace=str(workspace))
        result = await agent.run(
            issue_number=args.get("issue_number"),
            issue_text=args.get("issue_text", ""),
            auto_pr=args.get("auto_pr", False),
        )
        return {
            "success": result.success,
            "error": result.error,
            "plan": result.plan,
            "pr_url": result.pr_url,
        }

    try:
        return _asyncio.run(_run())
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "plan": "",
            "pr_url": "",
        }


def _cleanup_tasks() -> None:
    """Remove expired and excess completed tasks."""
    now = time.time()
    with _ASYNC_LOCK:
        expired = [
            k
            for k, v in _ASYNC_TASKS.items()
            if v.created_at > 0 and now - v.created_at > _TASK_TTL_SECONDS
        ]
        for k in expired:
            del _ASYNC_TASKS[k]
        if len(_ASYNC_TASKS) > _MAX_ASYNC_TASKS:
            done = sorted(
                [
                    (k, v)
                    for k, v in _ASYNC_TASKS.items()
                    if v.status in ("complete", "failed", "cancelled", "timed_out")
                ],
                key=lambda x: x[1].created_at,
            )
            while len(_ASYNC_TASKS) > _MAX_ASYNC_TASKS and done:
                del _ASYNC_TASKS[done.pop(0)[0]]


def _run_resolve_thread(task_id: str, args: dict) -> None:
    """Background thread: run DemoAgent and update task status."""
    with _ASYNC_LOCK:
        task = _ASYNC_TASKS.get(task_id)
        if task is None or task.cancelled:
            return
        task.status = "running"
        task.progress = "Initializing DemoAgent..."
    start = time.time()
    try:
        result = _dispatch_resolve_issue(args)
        elapsed = time.time() - start
        with _ASYNC_LOCK:
            task = _ASYNC_TASKS.get(task_id)
            if task is None:
                return
            if task.cancelled:
                task.status = "cancelled"
                task.progress = "Task was cancelled."
                return
            if elapsed > task.timeout:
                task.status = "timed_out"
                task.progress = f"Task exceeded {task.timeout}s timeout."
                task.result = result
                return
            task.status = "complete"
            task.progress = "Resolution complete."
            task.result = result
    except Exception as exc:
        logger.exception("Async resolve task %s failed", task_id)
        with _ASYNC_LOCK:
            task = _ASYNC_TASKS.get(task_id)
            if task is not None:
                task.status = "failed"
                task.progress = "Task failed."
                task.error = str(exc)


def _dispatch_resolve_issue_async(args: dict) -> dict:
    _cleanup_tasks()
    task_id = uuid.uuid4().hex
    task = _AsyncTask(
        task_id=task_id,
        status="queued",
        progress="Task queued.",
        created_at=time.time(),
        timeout=float(args.get("timeout", 300)),
        progress_token=args.get("progress_token", ""),
    )
    with _ASYNC_LOCK:
        _ASYNC_TASKS[task_id] = task
    thread = threading.Thread(
        target=_run_resolve_thread,
        args=(task_id, args),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id, "status": "queued"}


def _dispatch_resolve_issue_status(args: dict) -> dict:
    task_id = args["task_id"]
    with _ASYNC_LOCK:
        task = _ASYNC_TASKS.get(task_id)
        if task is None:
            return {"error": f"Task {task_id} not found"}
        return {
            "task_id": task.task_id,
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "error": task.error,
        }


def _dispatch_resolve_issue_cancel(args: dict) -> dict:
    task_id = args["task_id"]
    with _ASYNC_LOCK:
        task = _ASYNC_TASKS.get(task_id)
        if task is None:
            return {"error": f"Task {task_id} not found"}
        if task.status in ("complete", "failed", "cancelled", "timed_out"):
            return {
                "task_id": task_id,
                "status": task.status,
                "message": "Task already finished",
            }
        task.cancelled = True
        task.status = "cancelled"
        task.progress = "Task cancelled by user."
        return {"task_id": task_id, "status": "cancelled"}


def _dispatch_search(args: dict) -> dict:
    q = urllib.parse.quote(args["query"])
    limit = int(args.get("limit", 10))
    return _api("GET", f"/search/text?q={q}&limit={limit}")


def _dispatch_graph_relationships(args: dict) -> dict:
    eid = urllib.parse.quote(args["entity_id"])
    rtype = args.get("relation_type", "")
    qs = f"?relation_type={rtype}" if rtype else ""
    return _api("GET", f"/graph/entities/{eid}/relationships{qs}")


_DISPATCH_TABLE = {
    "loom_chat": lambda a: _api(
        "POST",
        "/llm/chat",
        {
            "messages": a["messages"],
            "model": a.get("model"),
            "temperature": a.get("temperature", 0.7),
            "max_tokens": a.get("max_tokens"),
        },
    ),
    "loom_list_models": lambda a: _api("GET", "/llm/models"),
    "loom_search": _dispatch_search,
    "loom_store": lambda a: _api(
        "POST",
        "/knowledge/documents",
        {
            "title": a["title"],
            "content": a["content"],
            "category": a.get("category", ""),
        },
    ),
    "loom_consensus": lambda a: _api(
        "POST",
        "/consensus/gather",
        {
            "messages": [{"role": "user", "content": a["prompt"]}],
            "models": a["models"],
        },
    ),
    "loom_synthesize": lambda a: _api(
        "POST",
        "/consensus/synthesize",
        {
            "prompt": a["prompt"],
            "models": a["models"],
            "arbiter_model": a.get("arbiter_model"),
        },
    ),
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
    "loom_graph_add_entity": lambda a: _api(
        "POST",
        "/graph/entities",
        {
            "label": a["label"],
            "entity_type": a["entity_type"],
            "properties": a.get("properties", {}),
        },
    ),
    "loom_graph_relationships": _dispatch_graph_relationships,
    "loom_router_select": lambda a: _api(
        "POST",
        "/router/select",
        {
            "task_type": a["task_type"],
        },
    ),
    "loom_router_stats": lambda a: _api("GET", "/router/performance"),
    "loom_health": lambda a: _api("GET", "/health"),
    "loom_resolve_issue": _dispatch_resolve_issue,
    "loom_resolve_issue_async": _dispatch_resolve_issue_async,
    "loom_resolve_issue_status": _dispatch_resolve_issue_status,
    "loom_resolve_issue_cancel": _dispatch_resolve_issue_cancel,
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
    with _MCP_STDOUT_LOCK:
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
        level=logging.WARNING,
        stream=sys.stderr,
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
            _respond(
                req_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "loom-ai",
                        "version": "1.0.0",
                    },
                },
            )
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
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            )


if __name__ == "__main__":
    main()
