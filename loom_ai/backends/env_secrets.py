"""Environment-variable secrets backend for loom-ai.

Reads secrets through a three-tier lookup:

1. In-memory overrides (set via ``set()`` or the *overrides* constructor arg)
2. A ``.env`` file (optional, parsed with a stdlib-only parser)
3. ``os.environ`` at call time

Writing (``set`` / ``delete``) mutates only the in-memory store; it
never touches ``os.environ`` or the ``.env`` file on disk.

Zero external dependencies -- stdlib only.
"""

from __future__ import annotations

import os
from pathlib import Path


class EnvSecretsBackend:
    """Three-tier secrets backend: overrides -> .env file -> os.environ.

    Satisfies :class:`~loom_ai.protocols.SecretsBackend` via structural
    subtyping.

    Parameters
    ----------
    env_file:
        Path to a ``.env`` file.  ``None`` disables file lookup.
    prefix:
        Optional key prefix (e.g. ``"APP_"``).  When set, a ``get("FOO")``
        call resolves to the environment variable ``APP_FOO``.
    overrides:
        Initial in-memory overrides that take priority over all other
        sources.
    """

    def __init__(
        self,
        env_file: str | None = None,
        prefix: str = "",
        overrides: dict[str, str] | None = None,
    ) -> None:
        self._env_file = env_file
        self._prefix = prefix

        # Mutable in-memory store (written by set/delete)
        self._store: dict[str, str] = dict(overrides) if overrides else {}

        # Lazily parsed .env cache
        self._dotenv: dict[str, str] = {}
        self._dotenv_loaded = False

    # ── helpers ──────────────────────────────────────────────────────

    def _ensure_dotenv(self) -> None:
        """Lazily parse the .env file (at most once)."""
        if self._dotenv_loaded:
            return
        self._dotenv_loaded = True

        if self._env_file is None:
            return
        path = Path(self._env_file).expanduser()
        if not path.is_file():
            return

        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Strip matching surrounding quotes
                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in ("'", '"')
                ):
                    value = value[1:-1]
                self._dotenv[key] = value

    def _prefixed(self, name: str) -> str:
        return f"{self._prefix}{name}" if self._prefix else name

    def _resolve(self, name: str) -> str | None:
        """Three-tier lookup: _store -> dotenv -> os.environ."""
        pname = self._prefixed(name)

        # 1. In-memory store (includes overrides + runtime set() calls)
        if pname in self._store:
            return self._store[pname]

        # 2. Dotenv file
        self._ensure_dotenv()
        if pname in self._dotenv:
            return self._dotenv[pname]

        # 3. Live environment
        return os.environ.get(pname)

    def _all_known_names(self) -> set[str]:
        """Collect every key visible across all three tiers."""
        self._ensure_dotenv()
        names: set[str] = set()
        prefix = self._prefix

        for source in (self._store, self._dotenv, os.environ):
            for key in source:
                if key.startswith(prefix):
                    names.add(key[len(prefix) :] if prefix else key)

        return names

    # ── SecretsBackend interface ─────────────────────────────────────

    async def get(self, name: str) -> str | None:
        """Return the secret value for *name*, or ``None``."""
        return self._resolve(name)

    async def set(self, name: str, value: str) -> bool:
        """Store a secret in the in-memory store.  Always returns ``True``."""
        self._store[self._prefixed(name)] = value
        return True

    async def list_names(self) -> list[str]:
        """Return every known secret name (across all tiers)."""
        return sorted(self._all_known_names())

    async def delete(self, name: str) -> bool:
        """Remove a secret from the in-memory store.

        Returns ``True`` if the key existed in the store and was removed.
        Does not touch ``os.environ`` or the ``.env`` file.
        """
        pname = self._prefixed(name)
        if pname in self._store:
            del self._store[pname]
            return True
        return False
