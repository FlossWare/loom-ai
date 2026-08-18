"""Tests for RotatingSecretsBackend (issue #292).

Verifies:
- Fallback chain (primary fails, secondary succeeds)
- Key rotation (old key replaced, new key returned)
- TTL expiry (expired keys return None)
- Validation callback (invalid values are skipped)
- list_names aggregation across backends and rotated keys
- delete clears rotation overrides and TTL
"""

from __future__ import annotations

import pytest

from loom_ai.backends.env_secrets import EnvSecretsBackend
from loom_ai.backends.rotating_secrets import RotatingSecretsBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FailingSecretsBackend:
    """Backend that raises on every operation."""

    async def get(self, name: str) -> str | None:
        raise RuntimeError(f"fail get {name}")

    async def set(self, name: str, value: str) -> None:
        raise RuntimeError(f"fail set {name}")

    async def delete(self, name: str) -> bool:
        raise RuntimeError(f"fail delete {name}")

    async def list_names(self) -> list[str]:
        raise RuntimeError("fail list")


class DictSecretsBackend:
    """Simple dict-backed secrets for testing."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data = dict(data or {})

    async def get(self, name: str) -> str | None:
        return self._data.get(name)

    async def set(self, name: str, value: str) -> None:
        self._data[name] = value

    async def delete(self, name: str) -> bool:
        if name in self._data:
            del self._data[name]
            return True
        return False

    async def list_names(self) -> list[str]:
        return sorted(self._data)
