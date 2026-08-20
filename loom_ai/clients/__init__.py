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

from loom_ai.clients.client import ClientConfig, LoomClient
from loom_ai.clients.local_client import LocalClient
from loom_ai.clients.transport_security import (
    allow_insecure_from_env,
    validate_api_key_transport,
)

# --- transport security (#669) ----------------------------------------
# Patch ClientConfig so API keys cannot be sent over plaintext HTTP to
# non-loopback hosts.  allow_insecure_http / LOOM_ALLOW_INSECURE_HTTP=1
# opts out explicitly.

_orig_from_env = ClientConfig.from_env
_orig_init = LoomClient.__init__


@classmethod  # type: ignore[misc]
def _from_env_secure(cls) -> ClientConfig:
    cfg = _orig_from_env()
    insecure = allow_insecure_from_env()
    # attach flag if dataclass doesn't have the field yet
    if not hasattr(cfg, "allow_insecure_http"):
        object.__setattr__(cfg, "allow_insecure_http", insecure)
    else:
        object.__setattr__(cfg, "allow_insecure_http", insecure)
    validate_api_key_transport(
        cfg.base_url, cfg.api_key, allow_insecure_http=insecure
    )
    return cfg


def _init_secure(self, config: ClientConfig | None = None) -> None:
    cfg = config or ClientConfig.from_env()
    insecure = bool(getattr(cfg, "allow_insecure_http", False))
    validate_api_key_transport(
        cfg.base_url, cfg.api_key, allow_insecure_http=insecure
    )
    _orig_init(self, cfg)


ClientConfig.from_env = _from_env_secure  # type: ignore[method-assign]
LoomClient.__init__ = _init_secure  # type: ignore[method-assign]

__all__ = ["LocalClient", "LoomClient", "ClientConfig", "get_client"]


async def get_client() -> LocalClient | LoomClient:
    """Auto-detect and return the appropriate client.

    Returns :class:`LoomClient` when ``LOOM_URL`` or ``LOOM_HOST`` is set
    (remote server mode), otherwise returns :class:`LocalClient` with
    embedded backends (local mode).
    """
    if os.environ.get("LOOM_URL") or os.environ.get("LOOM_HOST"):
        return LoomClient.from_env()
    return await LocalClient.create()
