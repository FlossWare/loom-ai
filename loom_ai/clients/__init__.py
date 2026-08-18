"""Loom-AI client implementations.

Provides a shared async SDK and adapters for integrating loom-ai with
external tools: standalone CLI, Crush, OpenCode, and any
OpenAI-compatible consumer.
"""

from __future__ import annotations

from loom_ai.clients.client import LoomClient

__all__ = ["LoomClient"]
