"""Tests for AdaptiveModelRouter -- Thompson Sampling model selection
with capability profiles, provider registration, and performance tracking.

No external dependencies beyond pytest / pytest-asyncio.
"""

from __future__ import annotations

import random

import pytest

from loom_ai.backends.adaptive_router import (
    AdaptiveModelRouter,
    ModelCapabilityProfile,
)
from loom_ai.models_phase1 import ModelInfo

# ── Mock backend ─────────────────────────────────────────────────────────


class MockBackend:
    def __init__(self, name: str) -> None:
        self.name = name

    async def chat(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        return None

    async def chat_stream(
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ):
        yield ""

    async def list_models(self) -> list[str]:
        return []


# ── Capability profiles ─────────────────────────────────────────────────


class TestCapabilityProfiles:
    def test_set_and_get_profile(self):
        router = AdaptiveModelRouter()
        profile = ModelCapabilityProfile(
            model="gpt-4o",
            capabilities=["code", "reasoning"],
            strengths={"code": 0.8},
        )
        router.set_profile("gpt-4o", profile)
        assert router.get_profile("gpt-4o") is profile

    def test_get_profile_nonexistent(self):
        router = AdaptiveModelRouter()
        assert router.get_profile("ghost") is None

    def test_models_for_task(self):
        router = AdaptiveModelRouter()
        router.set_profile(
            "gpt-4o",
            ModelCapabilityProfile(model="gpt-4o", capabilities=["code", "reasoning"]),
        )
        router.set_profile(
            "claude",
            ModelCapabilityProfile(model="claude", capabilities=["code", "chat"]),
        )
        router.set_profile(
            "gemini",
            ModelCapabilityProfile(model="gemini", capabilities=["chat"]),
        )

        code_models = router.models_for_task("code")
        assert set(code_models) == {"gpt-4o", "claude"}

        chat_models = router.models_for_task("chat")
        assert set(chat_models) == {"claude", "gemini"}

    def test_models_for_task_empty(self):
        router = AdaptiveModelRouter()
        assert router.models_for_task("nonexistent") == []


# ── Provider registration and routing ────────────────────────────────────


class TestProviderRouting:
    async def test_register_and_route(self):
        router = AdaptiveModelRouter()
        backend = MockBackend("openai")
        await router.register_provider("openai", backend, models=["gpt-4o"])

        result = await router.route("gpt-4o")
        assert result is backend

    async def test_route_unknown_model_raises(self):
        router = AdaptiveModelRouter()
        with pytest.raises(LookupError, match="No provider registered"):
            await router.route("nonexistent")

    async def test_priority_routing(self):
        router = AdaptiveModelRouter()
        low = MockBackend("low")
        high = MockBackend("high")

        await router.register_provider("low", low, models=["shared"], priority=1)
        await router.register_provider("high", high, models=["shared"], priority=10)

        result = await router.route("shared")
        assert result is high

    async def test_fallback_on_unhealthy(self):
        router = AdaptiveModelRouter()
        primary = MockBackend("primary")
        fallback = MockBackend("fallback")

        await router.register_provider("primary", primary, models=["m"], priority=10)
        await router.register_provider("fallback", fallback, models=["m"], priority=1)

        for _ in range(10):
            router.record_error("primary")

        result = await router.route("m", fallback=True)
        assert result is fallback

    async def test_fallback_disabled_raises(self):
        router = AdaptiveModelRouter()
        backend = MockBackend("bad")
        await router.register_provider("bad", backend, models=["m"])

        for _ in range(10):
            router.record_error("bad")

        with pytest.raises(LookupError, match="fallback disabled"):
            await router.route("m", fallback=False)

    async def test_list_available_models(self):
        router = AdaptiveModelRouter()
        await router.register_provider(
            "openai", MockBackend("openai"), models=["gpt-4o", "gpt-4o-mini"]
        )

        models = await router.list_available_models()
        names = {m.model for m in models}
        assert names == {"gpt-4o", "gpt-4o-mini"}

    async def test_provider_health(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["m"])
        router.record_success("p", latency_ms=100.0)
        router.record_error("p", latency_ms=200.0)

        health = await router.provider_health()
        assert "p" in health
        assert health["p"].error_rate == pytest.approx(0.5)

    async def test_estimate_cost(self):
        router = AdaptiveModelRouter()
        await router.register_provider(
            "openai", MockBackend("openai"), models=["gpt-4o"]
        )
        router.set_model_info(
            "gpt-4o",
            ModelInfo(model="gpt-4o", provider="openai", cost_per_1k_tokens=0.005),
        )
        cost = await router.estimate_cost("gpt-4o", 10000)
        assert cost == pytest.approx(0.05)

    async def test_estimate_cost_unknown_raises(self):
        router = AdaptiveModelRouter()
        with pytest.raises(LookupError):
            await router.estimate_cost("ghost", 1000)


# ── Thompson Sampling selection ──────────────────────────────────────────


class TestThompsonSampling:
    async def test_select_with_explicit_candidates(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["a", "b", "c"])

        result = await router.select("code", candidates=["a", "b", "c"])
        assert result in {"a", "b", "c"}

    async def test_select_auto_candidates_from_profiles(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["a", "b", "c"])
        router.set_profile(
            "a",
            ModelCapabilityProfile(model="a", capabilities=["code"]),
        )
        router.set_profile(
            "b",
            ModelCapabilityProfile(model="b", capabilities=["chat"]),
        )

        result = await router.select("code")
        assert result == "a"  # only "a" has "code" capability

    async def test_select_falls_back_to_all_models(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["x", "y"])
        # No profiles set -> falls back to all registered models
        result = await router.select("code")
        assert result in {"x", "y"}

    async def test_select_no_candidates_raises(self):
        router = AdaptiveModelRouter()
        with pytest.raises(ValueError, match="No candidate models"):
            await router.select("code", candidates=[])

    async def test_select_no_registered_models_raises(self):
        router = AdaptiveModelRouter()
        with pytest.raises(ValueError, match="No candidate models"):
            await router.select("code")

    async def test_select_favors_rewarded_model(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["good", "bad"])

        for _ in range(50):
            await router.record_outcome("good", "code", reward=1.0)
            await router.record_outcome("bad", "code", reward=0.0)

        counts = {"good": 0, "bad": 0}
        for _ in range(200):
            choice = await router.select("code", candidates=["good", "bad"])
            counts[choice] += 1

        assert counts["good"] > counts["bad"]

    async def test_select_deterministic_with_seed(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["a", "b"])

        random.seed(42)
        first = await router.select("code", candidates=["a", "b"])

        router2 = AdaptiveModelRouter()
        await router2.register_provider("p", MockBackend("p"), models=["a", "b"])
        random.seed(42)
        second = await router2.select("code", candidates=["a", "b"])

        assert first == second

    async def test_strength_prior_influences_selection(self):
        router = AdaptiveModelRouter()
        await router.register_provider("p", MockBackend("p"), models=["strong", "weak"])
        router.set_profile(
            "strong",
            ModelCapabilityProfile(
                model="strong",
                capabilities=["code"],
                strengths={"code": 0.95},
            ),
        )
        router.set_profile(
            "weak",
            ModelCapabilityProfile(
                model="weak",
                capabilities=["code"],
                strengths={"code": 0.05},
            ),
        )

        counts = {"strong": 0, "weak": 0}
        for _ in range(200):
            choice = await router.select("code")
            counts[choice] += 1

        assert counts["strong"] > counts["weak"]


# ── record_outcome and performance ───────────────────────────────────────


class TestOutcomeTracking:
    async def test_record_outcome_updates_arm(self):
        router = AdaptiveModelRouter()
        await router.record_outcome("gpt-4o", "code", reward=0.9)

        perf = await router.performance()
        arm = perf["gpt-4o:code"]
        assert arm["alpha"] == 2.0  # 1.0 prior + 1.0
        assert arm["beta"] == 1.0
        assert arm["successes"] == 1
        assert arm["total_trials"] == 1

    async def test_record_outcome_low_reward(self):
        router = AdaptiveModelRouter()
        await router.record_outcome("m", "code", reward=0.3)

        perf = await router.performance()
        arm = perf["m:code"]
        assert arm["alpha"] == 1.0
        assert arm["beta"] == 2.0
        assert arm["successes"] == 0

    async def test_performance_filter_by_task_type(self):
        router = AdaptiveModelRouter()
        await router.record_outcome("a", "code", reward=1.0)
        await router.record_outcome("b", "chat", reward=0.5)

        code_perf = await router.performance(task_type="code")
        assert len(code_perf) == 1
        assert "a:code" in code_perf

    async def test_performance_empty(self):
        router = AdaptiveModelRouter()
        perf = await router.performance()
        assert perf == {}

    async def test_avg_reward_computed(self):
        router = AdaptiveModelRouter()
        await router.record_outcome("m", "code", reward=1.0)
        await router.record_outcome("m", "code", reward=0.0)

        perf = await router.performance()
        assert perf["m:code"]["avg_reward"] == pytest.approx(0.5)

    async def test_multiple_models_independent(self):
        router = AdaptiveModelRouter()
        await router.record_outcome("a", "code", reward=1.0)
        await router.record_outcome("b", "code", reward=0.0)

        perf = await router.performance()
        assert perf["a:code"]["successes"] == 1
        assert perf["b:code"]["successes"] == 0


# ── ModelRouter protocol conformance ─────────────────────────────────────


class TestProtocolConformance:
    async def test_satisfies_model_router_protocol(self):
        from loom_ai.contracts_phase1 import ModelRouter

        router = AdaptiveModelRouter()
        assert isinstance(router, ModelRouter)
