"""API-key rotation and fallback-chain secrets backend for loom-ai.

Wraps one or more :class:`~loom_ai.protocols.SecretsBackend` instances
into a single backend that supports:

- **Fallback chain**: if the primary backend cannot resolve a key, the
  next backend in the chain is tried, and so on.
- **Key rotation**: mark a key as rotated so all subsequent reads
  transparently return the new value.
- **TTL expiry**: optionally attach a time-to-live to individual secrets
  so that expired entries are treated as absent.
- **Validation callback**: optionally validate secret values on retrieval.

Writing (``set`` / ``delete``) always targets the *first* backend in the
chain (the primary).

Zero external dependencies -- stdlib only.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from loom_ai.protocols import SecretsBackend


class RotatingSecretsBackend:
    """Fallback-chain secrets backend with rotation and TTL support.

    Satisfies :class:`~loom_ai.protocols.SecretsBackend` via structural
    subtyping.

    Parameters
    ----------
    backends:
        Ordered list of backends to consult.  The first entry is the
        *primary*; writes always target it.  Reads walk the chain until a
        value is found.
    validator:
        Optional callable ``(name, value) -> bool``.  When set, a
        retrieved value is only returned if the validator returns
        ``True``; otherwise the next backend in the chain is tried.
    """

    def __init__(
        self,
        backends: list[SecretsBackend],
        validator: Callable[[str, str], bool] | None = None,
    ) -> None:
        if not backends:
            raise ValueError("at least one backend is required")
        self._backends = list(backends)
        self._validator = validator

        # rotation overrides: name -> value
        self._rotated: dict[str, str] = {}

        # per-key TTL tracking: name -> expiry timestamp (monotonic)
        self._ttls: dict[str, float] = {}

    # -- rotation API --------------------------------------------------------

    def rotate(self, name: str, new_value: str) -> None:
        """Register *new_value* as the rotated replacement for *name*.

        Subsequent ``get`` calls return *new_value* immediately (before
        consulting any backend in the chain).  The old value in the
        primary backend is *not* deleted -- call ``delete`` explicitly
        if cleanup is needed.
        """
        self._rotated[name] = new_value

    def set_ttl(self, name: str, ttl_seconds: float) -> None:
        """Attach a TTL to *name*.

        After *ttl_seconds* from now the key is treated as expired:
        ``get`` returns ``None`` (or falls through to the next backend
        if no rotation override exists).
        """
        self._ttls[name] = time.monotonic() + ttl_seconds

    def _is_expired(self, name: str) -> bool:
        if name not in self._ttls:
            return False
        return time.monotonic() >= self._ttls[name]

    # -- SecretsBackend interface --------------------------------------------

    def _validate(self, name: str, value: str) -> bool:
        if self._is_expired(name):
            return False
        if self._validator and not self._validator(name, value):
            return False
        return True

    async def get(self, name: str) -> str | None:
        if name in self._rotated:
            value = self._rotated[name]
            return value if self._validate(name, value) else None

        for backend in self._backends:
            try:
                value = await backend.get(name)
            except Exception:
                continue
            if value is not None and self._validate(name, value):
                return value

        return None

    async def set(self, name: str, value: str) -> bool:
        return await self._backends[0].set(name, value)

    async def list_names(self) -> list[str]:
        seen: set[str] = set()
        for backend in self._backends:
            try:
                names = await backend.list_names()
            except Exception:
                continue
            seen.update(names)
        seen.update(self._rotated)
        return sorted(seen)

    async def delete(self, name: str) -> bool:
        self._rotated.pop(name, None)
        self._ttls.pop(name, None)
        return await self._backends[0].delete(name)
