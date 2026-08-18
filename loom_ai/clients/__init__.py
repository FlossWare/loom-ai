"""Loom-AI client implementations.

Provides a shared async SDK and adapters for integrating loom-ai with
external tools: standalone CLI, Crush, OpenCode, Aider, Cursor,
Continue.dev, and Claude Code.

Note: adapters that generate OpenAI-compatible configs point to
``/llm`` as the base URL.  The loom-ai server currently serves
``/llm/chat`` and ``/llm/models`` — it does **not** serve the
``/v1/chat/completions`` route some tools append automatically.
An OpenAI-compatible proxy layer is planned for a future release.
"""

from __future__ import annotations

import os

from loom_ai.clients.client import LoomClient
from loom_ai.clients.local_client import LocalClient

__all__ = ["LocalClient", "LoomClient", "get_client"]


async def get_client() -> LocalClient | LoomClient:
    """Auto-detect and return the appropriate client.

    Returns :class:`LoomClient` when ``LOOM_URL`` or ``LOOM_HOST`` is set
    (remote server mode), otherwise returns :class:`LocalClient` with
    embedded backends (local mode).
    """
    if os.environ.get("LOOM_URL") or os.environ.get("LOOM_HOST"):
        return LoomClient.from_env()
    return await LocalClient.create()
