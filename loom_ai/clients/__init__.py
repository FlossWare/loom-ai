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

from loom_ai.clients.client import LoomClient

__all__ = ["LoomClient"]
