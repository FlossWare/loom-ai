"""Tests for SimpleSessionInitializer backend.

Covers: default init, init with context override, timestamp is set,
protocol conformance, backend integration, and preferences merging.
No external dependencies required.
"""

from __future__ import annotations

from loom_ai.backends.session import SimpleSessionInitializer
from loom_ai.contracts_phase3 import SessionInitializer
from loom_ai.models_phase3 import SessionBriefing

# ── helpers ──────────────────────────────────────────────────────────────


class FakeMemoryBackend:
    """Minimal async memory backend for testing."""

    def __init__(self, documents: list | None = None) -> None:
        self._documents = documents or []

    async def list_documents(self, *, limit: int = 100) -> list:
        return self._documents[:limit]


class FakeSecretsBackend:
    """Minimal async secrets backend for testing."""

    def __init__(self, names: list[str] | None = None) -> None:
        self._names = names or []

    async def list_names(self) -> list[str]:
        return list(self._names)


# ── tests ────────────────────────────────────────────────────────────────


def test_protocol_conformance():
    """SimpleSessionInitializer satisfies the SessionInitializer protocol."""
    init = SimpleSessionInitializer()
    assert isinstance(init, SessionInitializer)


async def test_default_init():
    """No backends configured returns empty defaults with a timestamp."""
    init = SimpleSessionInitializer()
    briefing = await init.initialize()

    assert isinstance(briefing, SessionBriefing)
    assert briefing.memories == []
    assert briefing.fleet_status == {}
    assert briefing.preferences == {}
    assert briefing.api_keys == []
    assert briefing.initialized_at != ""


async def test_timestamp_is_set():
    """initialized_at contains a valid ISO-format UTC timestamp."""
    init = SimpleSessionInitializer()
    briefing = await init.initialize()

    # Should contain a 'T' (ISO separator) and timezone info
    assert "T" in briefing.initialized_at
    assert "+" in briefing.initialized_at or "Z" in briefing.initialized_at


async def test_context_override_memories():
    """Context dict overrides memories."""
    init = SimpleSessionInitializer()
    ctx = {"memories": ["custom-memory-1", "custom-memory-2"]}
    briefing = await init.initialize(context=ctx)

    assert briefing.memories == ["custom-memory-1", "custom-memory-2"]


async def test_context_override_fleet_status():
    """Context dict overrides fleet_status."""
    init = SimpleSessionInitializer(fleet_endpoint="http://example.com:5000")
    ctx = {"fleet_status": {"endpoint": "http://override:9000", "available": False}}
    briefing = await init.initialize(context=ctx)

    assert briefing.fleet_status == {
        "endpoint": "http://override:9000",
        "available": False,
    }


async def test_context_override_preferences():
    """Context dict overrides preferences."""
    init = SimpleSessionInitializer(preferences={"theme": "dark"})
    ctx = {"preferences": {"theme": "light", "verbose": True}}
    briefing = await init.initialize(context=ctx)

    assert briefing.preferences == {"theme": "light", "verbose": True}


async def test_context_override_api_keys():
    """Context dict overrides api_keys."""
    init = SimpleSessionInitializer()
    ctx = {"api_keys": ["key-1", "key-2"]}
    briefing = await init.initialize(context=ctx)

    assert briefing.api_keys == ["key-1", "key-2"]


async def test_memory_backend_integration():
    """Memory backend documents appear in briefing.memories."""
    docs = [{"id": "doc-1", "title": "Readme"}]
    init = SimpleSessionInitializer(memory_backend=FakeMemoryBackend(docs))
    briefing = await init.initialize()

    assert briefing.memories == docs


async def test_fleet_endpoint():
    """Fleet endpoint is recorded in fleet_status."""
    init = SimpleSessionInitializer(fleet_endpoint="http://fleet:5000")
    briefing = await init.initialize()

    assert briefing.fleet_status == {
        "endpoint": "http://fleet:5000",
        "available": True,
    }


async def test_preferences_passthrough():
    """Static preferences are passed into the briefing."""
    prefs = {"multi_ai": True, "cost_limit": 0}
    init = SimpleSessionInitializer(preferences=prefs)
    briefing = await init.initialize()

    assert briefing.preferences == {"multi_ai": True, "cost_limit": 0}


async def test_secrets_backend_integration():
    """Secrets backend names appear in briefing.api_keys."""
    init = SimpleSessionInitializer(
        secrets_backend=FakeSecretsBackend(["OPENAI_KEY", "ANTHROPIC_KEY"])
    )
    briefing = await init.initialize()

    assert briefing.api_keys == ["OPENAI_KEY", "ANTHROPIC_KEY"]


async def test_all_backends_together():
    """All backends configured at once produce a complete briefing."""
    init = SimpleSessionInitializer(
        memory_backend=FakeMemoryBackend(["mem-1"]),
        fleet_endpoint="http://aio-01:5000",
        preferences={"mode": "fleet"},
        secrets_backend=FakeSecretsBackend(["KEY_A"]),
    )
    briefing = await init.initialize()

    assert briefing.memories == ["mem-1"]
    assert briefing.fleet_status["endpoint"] == "http://aio-01:5000"
    assert briefing.preferences == {"mode": "fleet"}
    assert briefing.api_keys == ["KEY_A"]
    assert briefing.initialized_at != ""


async def test_context_none_is_noop():
    """Passing context=None does not alter defaults."""
    init = SimpleSessionInitializer(preferences={"x": 1})
    briefing = await init.initialize(context=None)

    assert briefing.preferences == {"x": 1}


async def test_context_non_dict_is_ignored():
    """Non-dict context values do not cause errors."""
    init = SimpleSessionInitializer()
    briefing = await init.initialize(context="some-string")

    assert isinstance(briefing, SessionBriefing)
    assert briefing.memories == []


async def test_preferences_not_mutated():
    """The original preferences dict is not mutated by initialize calls."""
    original = {"key": "value"}
    init = SimpleSessionInitializer(preferences=original)

    await init.initialize(context={"preferences": {"key": "override"}})

    # The next call without context should still have the original
    briefing = await init.initialize()
    assert briefing.preferences == {"key": "value"}
