"""Simple session initializer backend for loom-ai.

Builds a :class:`~loom_ai.models_phase3.SessionBriefing` by gathering
context from optionally configured backends (memory, fleet, secrets) and
merging caller-supplied overrides.

When no backends are configured the initializer still returns a valid
briefing with empty defaults and a timestamp -- making it safe to use as
a zero-config fallback.

Zero external dependencies -- stdlib only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loom_ai.models_phase3 import SessionBriefing


class SimpleSessionInitializer:
    """Configurable session bootstrap.

    Satisfies :class:`~loom_ai.contracts_phase3.SessionInitializer` via
    structural subtyping.

    Parameters
    ----------
    memory_backend:
        Any object with an async ``list_documents(limit=...)`` method.
        When provided, the briefing's *memories* list is populated from
        the returned documents.
    fleet_endpoint:
        URL string for a fleet controller.  Stored in *fleet_status* as
        ``{"endpoint": ..., "available": True}``.  No HTTP calls are
        made -- the endpoint is recorded for downstream consumers.
    preferences:
        Static preference dict merged into the briefing.
    secrets_backend:
        Any object with an async ``list_names()`` method.  When
        provided, the briefing's *api_keys* list is populated from the
        returned secret names.
    """

    def __init__(
        self,
        *,
        memory_backend: Any | None = None,
        fleet_endpoint: str | None = None,
        preferences: dict | None = None,
        secrets_backend: Any | None = None,
    ) -> None:
        self._memory_backend = memory_backend
        self._fleet_endpoint = fleet_endpoint
        self._preferences = dict(preferences) if preferences else {}
        self._secrets_backend = secrets_backend

    async def initialize(self, *, context: Any | None = None) -> SessionBriefing:
        """Build a :class:`SessionBriefing` from configured backends.

        *context*, when supplied as a dict, may contain keys that
        override the corresponding briefing fields: ``memories``,
        ``fleet_status``, ``preferences``, ``api_keys``.
        """
        memories: list = []
        fleet_status: dict = {}
        preferences: dict = dict(self._preferences)
        api_keys: list[str] = []

        # -- gather from backends ----------------------------------------
        if self._memory_backend is not None:
            memories = await self._memory_backend.list_documents(limit=100)

        if self._fleet_endpoint is not None:
            fleet_status = {
                "endpoint": self._fleet_endpoint,
                "available": True,
            }

        if self._secrets_backend is not None:
            api_keys = await self._secrets_backend.list_names()

        # -- apply context overrides -------------------------------------
        if isinstance(context, dict):
            if "memories" in context:
                memories = context["memories"]
            if "fleet_status" in context:
                fleet_status = context["fleet_status"]
            if "preferences" in context:
                preferences = context["preferences"]
            if "api_keys" in context:
                api_keys = context["api_keys"]

        return SessionBriefing(
            memories=memories,
            fleet_status=fleet_status,
            preferences=preferences,
            api_keys=api_keys,
            initialized_at=datetime.now(timezone.utc).isoformat(),
        )
