"""Tests for the Thompson Sampling model router REST endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed (server extra)")

from fastapi.testclient import TestClient  # noqa: E402

from loom_ai.backends.adaptive_router import AdaptiveModelRouter  # noqa: E402
from loom_ai.config import LoomConfig  # noqa: E402
from loom_ai.server import create_app  # noqa: E402


def _make_client(monkeypatch) -> TestClient:
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LOOM_ROUTER", "adaptive")
    import asyncio

    cfg = asyncio.run(LoomConfig.from_env())
    return TestClient(create_app(cfg))


def _seeded_client(monkeypatch) -> TestClient:
    """Client with two models pre-registered and profiled."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
    import asyncio

    from loom_ai.backends.adaptive_router import ModelCapabilityProfile

    router = AdaptiveModelRouter()
    asyncio.run(
        router.register_provider("openai", None, models=["gpt-4o", "gpt-4o-mini"])
    )
    asyncio.run(router.register_provider("google", None, models=["gemini-flash"]))
    router.set_profile(
        "gpt-4o",
        ModelCapabilityProfile(
            model="gpt-4o",
            capabilities=["code", "reasoning", "chat"],
            strengths={"code": 0.9, "reasoning": 0.8},
        ),
    )
    router.set_profile(
        "gemini-flash",
        ModelCapabilityProfile(
            model="gemini-flash",
            capabilities=["chat", "summarization"],
            strengths={"chat": 0.7},
        ),
    )

    from loom_ai.backends.env_secrets import EnvSecretsBackend
    from loom_ai.backends.memory import (
        MemoryQueueBackend,
        MemorySearchBackend,
        MemoryStorageBackend,
        NoopEmbeddingBackend,
    )

    cfg = LoomConfig(
        storage=MemoryStorageBackend(),
        queue=MemoryQueueBackend(),
        secrets=EnvSecretsBackend(),
        embedding=NoopEmbeddingBackend(),
        search=MemorySearchBackend(),
        router=router,
    )
    return TestClient(create_app(cfg))


class TestRouterSelect:
    def test_select_from_candidates(self, monkeypatch):
        client = _make_client(monkeypatch)
        client.post(
            "/router/register",
            json={
                "provider_name": "test",
                "models": ["model-a", "model-b"],
            },
        )
        resp = client.post(
            "/router/select",
            json={
                "task_type": "code",
                "candidates": ["model-a", "model-b"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] in ("model-a", "model-b")
        assert body["task_type"] == "code"

    def test_select_with_profiles(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        resp = client.post("/router/select", json={"task_type": "code"})
        assert resp.status_code == 200
        assert resp.json()["model"] == "gpt-4o"

    def test_select_no_candidates_400(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.post(
            "/router/select",
            json={
                "task_type": "code",
                "candidates": [],
            },
        )
        assert resp.status_code == 400

    def test_select_unknown_task_falls_back(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        resp = client.post("/router/select", json={"task_type": "unknown"})
        assert resp.status_code == 200
        assert resp.json()["model"] in ("gpt-4o", "gpt-4o-mini", "gemini-flash")


class TestRouterOutcome:
    def test_record_outcome(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        resp = client.post(
            "/router/outcome",
            json={
                "model": "gpt-4o",
                "task_type": "code",
                "reward": 0.9,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["recorded"] is True

    def test_reward_out_of_range_422(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        resp = client.post(
            "/router/outcome",
            json={
                "model": "gpt-4o",
                "task_type": "code",
                "reward": 1.5,
            },
        )
        assert resp.status_code == 422

    def test_outcome_updates_performance(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        client.post(
            "/router/outcome",
            json={
                "model": "gpt-4o",
                "task_type": "code",
                "reward": 0.95,
            },
        )
        client.post(
            "/router/outcome",
            json={
                "model": "gpt-4o",
                "task_type": "code",
                "reward": 0.2,
            },
        )
        resp = client.get("/router/performance", params={"task_type": "code"})
        assert resp.status_code == 200
        arms = resp.json()["arms"]
        arm = arms["gpt-4o:code"]
        assert arm["total_trials"] == 2
        assert arm["successes"] == 1


class TestRouterManagement:
    def test_register_provider(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.post(
            "/router/register",
            json={
                "provider_name": "groq",
                "models": ["llama-70b", "mixtral-8x7b"],
                "priority": 5,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["models_registered"] == 2

    def test_set_profile(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.post(
            "/router/profile",
            json={
                "model": "llama-70b",
                "capabilities": ["code", "reasoning"],
                "strengths": {"code": 0.7},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["capabilities"] == ["code", "reasoning"]

    def test_list_models(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        resp = client.get("/router/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        model_names = {m["model"] for m in body["models"]}
        assert "gpt-4o" in model_names
        assert "gemini-flash" in model_names

    def test_provider_health(self, monkeypatch):
        client = _seeded_client(monkeypatch)
        resp = client.get("/router/health")
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        assert "openai" in providers
        assert providers["openai"]["healthy"] is True

    def test_performance_empty(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.get("/router/performance")
        assert resp.status_code == 200
        assert resp.json()["arms"] == {}


class TestRouterDisabled:
    def test_no_routes_when_disabled(self, monkeypatch):
        monkeypatch.delenv("LOOM_API_KEY", raising=False)
        monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("LOOM_ROUTER", "disabled")
        import asyncio

        cfg = asyncio.run(LoomConfig.from_env())
        client = TestClient(create_app(cfg))
        resp = client.post("/router/select", json={"task_type": "code"})
        assert resp.status_code == 404


class TestHealthIncludesRouter:
    def test_health_shows_router_enabled(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["backends"]["router"] == "AdaptiveModelRouter"

    def test_health_shows_router_disabled(self, monkeypatch):
        monkeypatch.delenv("LOOM_API_KEY", raising=False)
        monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("LOOM_ROUTER", "disabled")
        import asyncio

        cfg = asyncio.run(LoomConfig.from_env())
        client = TestClient(create_app(cfg))
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["backends"]["router"] == "disabled"
