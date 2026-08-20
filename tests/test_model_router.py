"""Tests for SimpleModelRouter: registration, priority routing,
fallback on failure, model listing, health tracking, and cost
estimation.
"""

import pytest

from loom_ai.backends.router import SimpleModelRouter
from loom_ai.models_core import ModelInfo

# ── Mock backends ────────────────────────────────────────────────────────


class MockBackend:
    """Minimal LLMBackend stub that records which models it was asked for."""

    def __init__(self, name: str, models: list[str] | None = None) -> None:
        self.name = name
        self._models = models or []

    async def chat(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        return None  # not exercised in routing tests

    async def chat_stream(
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ):
        yield ""  # not exercised in routing tests

    async def list_models(self) -> list[str]:
        return list(self._models)


class FailingBackend:
    """Backend whose calls always raise -- used to simulate provider outage."""

    async def chat(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        raise RuntimeError("provider down")

    async def chat_stream(
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ):
        raise RuntimeError("provider down")

    async def list_models(self) -> list[str]:
        return []


# ── Registration and basic routing ───────────────────────────────────────


async def test_register_and_route():
    """Registering a provider makes its models routable."""
    router = SimpleModelRouter()
    backend = MockBackend("openai", ["gpt-4o"])
    await router.register_provider("openai", backend, models=["gpt-4o"])

    result = await router.route("gpt-4o")
    assert result is backend


async def test_route_unknown_model_raises():
    """Routing an unregistered model raises LookupError."""
    router = SimpleModelRouter()
    with pytest.raises(LookupError, match="No provider registered"):
        await router.route("nonexistent-model")


async def test_register_multiple_providers():
    """Multiple providers can serve different models."""
    router = SimpleModelRouter()
    openai = MockBackend("openai")
    google = MockBackend("google")

    await router.register_provider("openai", openai, models=["gpt-4o"])
    await router.register_provider("google", google, models=["gemini-pro"])

    assert await router.route("gpt-4o") is openai
    assert await router.route("gemini-pro") is google


# ── Priority ordering ────────────────────────────────────────────────────


async def test_priority_higher_wins():
    """When two providers serve the same model, higher priority wins."""
    router = SimpleModelRouter()
    low = MockBackend("low")
    high = MockBackend("high")

    await router.register_provider("low", low, models=["shared-model"], priority=1)
    await router.register_provider("high", high, models=["shared-model"], priority=10)

    result = await router.route("shared-model")
    assert result is high


async def test_priority_equal_returns_one():
    """Equal-priority providers both serve the model; one is returned."""
    router = SimpleModelRouter()
    a = MockBackend("a")
    b = MockBackend("b")

    await router.register_provider("a", a, models=["model-x"], priority=5)
    await router.register_provider("b", b, models=["model-x"], priority=5)

    result = await router.route("model-x")
    assert result is a or result is b


# ── Fallback behaviour ──────────────────────────────────────────────────


async def test_fallback_to_lower_priority():
    """When the primary provider is unhealthy, fallback=True picks the next."""
    router = SimpleModelRouter()
    primary = MockBackend("primary")
    fallback = MockBackend("fallback")

    await router.register_provider("primary", primary, models=["model-a"], priority=10)
    await router.register_provider("fallback", fallback, models=["model-a"], priority=1)

    # Simulate primary going unhealthy (>50% error rate)
    for _ in range(10):
        router.record_error("primary")

    result = await router.route("model-a", fallback=True)
    assert result is fallback


async def test_fallback_disabled_raises():
    """When fallback=False and the primary is unhealthy, LookupError is raised."""
    router = SimpleModelRouter()
    backend = MockBackend("bad")

    await router.register_provider("bad", backend, models=["model-b"], priority=10)
    for _ in range(10):
        router.record_error("bad")

    with pytest.raises(LookupError, match="fallback disabled"):
        await router.route("model-b", fallback=False)


async def test_fallback_all_unhealthy_returns_highest_priority():
    """When all providers are unhealthy and fallback=True, return highest priority."""
    router = SimpleModelRouter()
    primary = MockBackend("primary")
    secondary = MockBackend("secondary")

    await router.register_provider("primary", primary, models=["model-c"], priority=10)
    await router.register_provider(
        "secondary", secondary, models=["model-c"], priority=1
    )

    for _ in range(10):
        router.record_error("primary")
        router.record_error("secondary")

    result = await router.route("model-c", fallback=True)
    assert result is primary


# ── list_available_models ────────────────────────────────────────────────


async def test_list_available_models_empty():
    """No models registered returns an empty list."""
    router = SimpleModelRouter()
    models = await router.list_available_models()
    assert models == []


async def test_list_available_models():
    """All registered models appear in the listing."""
    router = SimpleModelRouter()
    await router.register_provider(
        "openai", MockBackend("openai"), models=["gpt-4o", "gpt-4o-mini"]
    )
    await router.register_provider(
        "google", MockBackend("google"), models=["gemini-pro"]
    )

    models = await router.list_available_models()
    names = {m.model for m in models}
    assert names == {"gpt-4o", "gpt-4o-mini", "gemini-pro"}
    assert all(isinstance(m, ModelInfo) for m in models)


async def test_list_available_models_with_enriched_info():
    """set_model_info enrichment appears in list_available_models."""
    router = SimpleModelRouter()
    await router.register_provider(
        "anthropic", MockBackend("anthropic"), models=["claude-sonnet"]
    )
    router.set_model_info(
        "claude-sonnet",
        ModelInfo(
            model="claude-sonnet",
            provider="anthropic",
            capabilities=["chat", "code"],
            context_length=200000,
            cost_per_1k_tokens=0.003,
        ),
    )

    models = await router.list_available_models()
    assert len(models) == 1
    info = models[0]
    assert info.capabilities == ["chat", "code"]
    assert info.context_length == 200000
    assert info.cost_per_1k_tokens == 0.003


# ── provider_health ──────────────────────────────────────────────────────


async def test_provider_health_initial():
    """A freshly registered provider is healthy with zero stats."""
    router = SimpleModelRouter()
    await router.register_provider(
        "test-provider", MockBackend("t"), models=["model-t"]
    )

    health = await router.provider_health()
    assert "test-provider" in health
    status = health["test-provider"]
    assert status.healthy is True
    assert status.error_rate == 0.0
    assert status.avg_latency_ms == 0.0
    assert status.models == ["model-t"]


async def test_provider_health_after_calls():
    """Health stats reflect recorded successes and errors."""
    router = SimpleModelRouter()
    await router.register_provider("p", MockBackend("p"), models=["m"])

    router.record_success("p", latency_ms=100.0)
    router.record_success("p", latency_ms=200.0)
    router.record_error("p", latency_ms=50.0)

    health = await router.provider_health()
    status = health["p"]
    assert status.error_rate == pytest.approx(1.0 / 3.0)
    assert status.avg_latency_ms == pytest.approx(350.0 / 3.0)
    assert status.healthy is True  # 33% < 50% threshold


async def test_provider_health_unhealthy():
    """A provider with >50% errors is marked unhealthy."""
    router = SimpleModelRouter()
    await router.register_provider("bad", MockBackend("bad"), models=["m"])

    router.record_success("bad")
    router.record_error("bad")
    router.record_error("bad")

    health = await router.provider_health()
    assert health["bad"].healthy is False


# ── estimate_cost ────────────────────────────────────────────────────────


async def test_estimate_cost():
    """Cost estimation uses cost_per_1k_tokens from ModelInfo."""
    router = SimpleModelRouter()
    await router.register_provider("openai", MockBackend("openai"), models=["gpt-4o"])
    router.set_model_info(
        "gpt-4o",
        ModelInfo(
            model="gpt-4o",
            provider="openai",
            cost_per_1k_tokens=0.005,
        ),
    )

    cost = await router.estimate_cost("gpt-4o", 10000)
    assert cost == pytest.approx(0.05)


async def test_estimate_cost_zero():
    """Default cost_per_1k_tokens is zero, so estimate is zero."""
    router = SimpleModelRouter()
    await router.register_provider("p", MockBackend("p"), models=["m"])

    cost = await router.estimate_cost("m", 5000)
    assert cost == 0.0


async def test_estimate_cost_unknown_model():
    """Estimating cost for an unknown model raises LookupError."""
    router = SimpleModelRouter()
    with pytest.raises(LookupError, match="No model info"):
        await router.estimate_cost("ghost", 1000)


# ── Protocol conformance ────────────────────────────────────────────────


async def test_satisfies_model_router_protocol():
    """SimpleModelRouter satisfies the ModelRouter protocol."""
    from loom_ai.contracts_core import ModelRouter

    router = SimpleModelRouter()
    assert isinstance(router, ModelRouter)
