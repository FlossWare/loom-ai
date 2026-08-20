"""Transport security helpers for LoomClient."""

from __future__ import annotations

import logging
import os
import urllib.parse

logger = logging.getLogger(__name__)


def allow_insecure_from_env() -> bool:
    return os.environ.get("LOOM_ALLOW_INSECURE_HTTP", "").lower() in (
        "1",
        "true",
        "yes",
    )


def validate_api_key_transport(
    base_url: str,
    api_key: str,
    *,
    allow_insecure_http: bool = False,
) -> None:
    """Reject API keys over plaintext HTTP to non-loopback hosts."""
    if not api_key:
        return
    url = base_url.strip()
    if url.lower().startswith("https://"):
        return
    if not url.lower().startswith("http://"):
        return
    if allow_insecure_http:
        logger.warning(
            "LOOM_ALLOW_INSECURE_HTTP enabled: sending API key over HTTP to %s",
            base_url,
        )
        return
    host = urllib.parse.urlparse(url).hostname or ""
    loopback = host in {
        "127.0.0.1",
        "localhost",
        "::1",
        "0:0:0:0:0:0:0:1",
    }
    if loopback:
        return
    raise ValueError(
        f"refusing to send API key over plaintext HTTP to {base_url!r}; "
        "use https:// or set LOOM_ALLOW_INSECURE_HTTP=1 for explicit override"
    )
