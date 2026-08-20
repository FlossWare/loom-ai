"""Bind and transport security helpers for the Loom server and client."""

from __future__ import annotations

_LOOPBACK_HOSTS = frozenset(
    {
        "127.0.0.1",
        "localhost",
        "::1",
        "0:0:0:0:0:0:0:1",
        "[::1]",
    }
)


def is_loopback_host(host: str) -> bool:
    """Return True for IPv4/IPv6 loopback and localhost names."""
    h = host.strip().lower()
    if h in _LOOPBACK_HOSTS:
        return True
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in _LOOPBACK_HOSTS


def require_api_key_for_non_loopback(host: str, api_key: str | None) -> None:
    """Fail closed when binding off-loopback without LOOM_API_KEY."""
    if is_loopback_host(host):
        return
    if api_key:
        return
    raise SystemExit(
        f"LOOM_HOST={host!r} is not loopback; set LOOM_API_KEY before binding. "
        "Unauthenticated binds are only allowed on 127.0.0.1 / ::1 / localhost."
    )
