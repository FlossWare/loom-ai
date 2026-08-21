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
_MCP_TASK_CATEGORY = "mcp_task"
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
