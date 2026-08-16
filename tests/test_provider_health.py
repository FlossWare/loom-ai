"""Tests for provider health tracking, rate limiting, and the composite
ResilientProvider guard.

No external dependencies beyond pytest / pytest-asyncio.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from loom_ai.backends.provider_health import (
    HealthSnapshot,
    ProviderHealthTracker,
    RateLimiter,
    ResilientProvider,
)

# ── ProviderHealthTracker ─────────────────────────────────────────────────


class TestProviderHealthTracker:
    """Tests for the rolling-window health tracker."""

    def test_snapshot_empty_provider(self):
        tracker = ProviderHealthTracker()
        snap = tracker.snapshot("openai")
        assert snap.provider == "openai"
        assert snap.total_requests == 0
        assert snap.avg_latency_ms == 0.0
        assert snap.error_rate == 0.0

    def test_record_success_updates_snapshot(self):
        tracker = ProviderHealthTracker()
        tracker.record("openai", success=True, latency_ms=100.0)
        tracker.record("openai", success=True, latency_ms=200.0)

        snap = tracker.snapshot("openai")
        assert snap.total_requests == 2
        assert snap.avg_latency_ms == pytest.approx(150.0)
        assert snap.error_rate == 0.0

    def test_record_errors_tracked(self):
        tracker = ProviderHealthTracker()
        tracker.record("openai", success=True, latency_ms=100.0)
        tracker.record("openai", success=False, latency_ms=500.0)

        snap = tracker.snapshot("openai")
        assert snap.total_requests == 2
        assert snap.error_rate == pytest.approx(0.5)

    def test_p95_latency(self):
        tracker = ProviderHealthTracker()
        # Record 20 requests: 19 at 100ms, 1 at 1000ms
        for _ in range(19):
            tracker.record("p", success=True, latency_ms=100.0)
        tracker.record("p", success=True, latency_ms=1000.0)

        snap = tracker.snapshot("p")
        assert snap.total_requests == 20
        assert snap.p95_latency_ms == 1000.0

    def test_rate_limit_headers_parsed(self):
        tracker = ProviderHealthTracker()
        tracker.record(
            "openai",
            success=True,
            latency_ms=50.0,
            headers={
                "X-RateLimit-Remaining": "42",
                "X-RateLimit-Reset": "1700000000.0",
            },
        )

        snap = tracker.snapshot("openai")
        assert snap.rate_limit_remaining == 42
        assert snap.rate_limit_reset_at == pytest.approx(1700000000.0)

    def test_rate_limit_headers_case_insensitive(self):
        tracker = ProviderHealthTracker()
        tracker.record(
            "p",
            success=True,
            latency_ms=10.0,
            headers={"x-ratelimit-remaining": "5"},
        )
        snap = tracker.snapshot("p")
        assert snap.rate_limit_remaining == 5

    def test_invalid_headers_ignored(self):
        tracker = ProviderHealthTracker()
        tracker.record(
            "p",
            success=True,
            latency_ms=10.0,
            headers={"X-RateLimit-Remaining": "not-a-number"},
        )
        snap = tracker.snapshot("p")
        assert snap.rate_limit_remaining is None

    def test_window_pruning(self):
        tracker = ProviderHealthTracker(window_seconds=10.0)
        with patch("loom_ai.backends.provider_health.time") as mock_time:
            mock_time.time.return_value = 100.0
            tracker.record("p", success=True, latency_ms=50.0)

            mock_time.time.return_value = 105.0
            tracker.record("p", success=False, latency_ms=200.0)

            # Move past the window
            mock_time.time.return_value = 115.0
            snap = tracker.snapshot("p")
            # Only the second record (at t=105) should remain
            assert snap.total_requests == 1
            assert snap.error_rate == pytest.approx(1.0)

    def test_providers_independent(self):
        tracker = ProviderHealthTracker()
        tracker.record("openai", success=True, latency_ms=100.0)
        tracker.record("anthropic", success=False, latency_ms=200.0)

        snap_openai = tracker.snapshot("openai")
        snap_anthropic = tracker.snapshot("anthropic")
        assert snap_openai.error_rate == 0.0
        assert snap_anthropic.error_rate == 1.0

    def test_snapshot_returns_health_snapshot_type(self):
        tracker = ProviderHealthTracker()
        snap = tracker.snapshot("p")
        assert isinstance(snap, HealthSnapshot)


# ── RateLimiter ──────────────────────────────────────────────────────────


class TestRateLimiter:
    """Tests for the token-bucket rate limiter."""

    def test_acquire_allowed_by_default(self):
        rl = RateLimiter(default_rpm=60)
        assert rl.acquire("openai") is True

    def test_acquire_drains_bucket(self):
        rl = RateLimiter(default_rpm=2)
        assert rl.acquire("p") is True
        assert rl.acquire("p") is True
        assert rl.acquire("p") is False

    def test_configure_overrides_default(self):
        rl = RateLimiter(default_rpm=60)
        rl.configure("slow", rpm=1)
        assert rl.acquire("slow") is True
        assert rl.acquire("slow") is False

    def test_tokens_refill_over_time(self):
        rl = RateLimiter(default_rpm=60)
        with patch("loom_ai.backends.provider_health.time") as mock_time:
            mock_time.time.return_value = 100.0
            # Drain all tokens
            for _ in range(60):
                rl.acquire("p")
            assert rl.acquire("p") is False

            # Advance 1 second -> 1 token should refill (60 rpm = 1/sec)
            mock_time.time.return_value = 101.0
            assert rl.acquire("p") is True

    def test_providers_independent(self):
        rl = RateLimiter(default_rpm=1)
        assert rl.acquire("a") is True
        assert rl.acquire("a") is False
        # Provider "b" has its own bucket
        assert rl.acquire("b") is True

    def test_update_from_headers_drains_on_zero_remaining(self):
        rl = RateLimiter(default_rpm=60)
        # Initial acquire to initialize the bucket
        rl.acquire("p")
        rl.update_from_headers(
            "p",
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "9999999999.0",
            },
        )
        assert rl.acquire("p") is False

    def test_update_from_headers_nonzero_remaining_no_drain(self):
        rl = RateLimiter(default_rpm=60)
        rl.acquire("p")  # initialize
        rl.update_from_headers("p", {"X-RateLimit-Remaining": "10"})
        # Bucket should still have tokens
        assert rl.acquire("p") is True

    def test_update_from_headers_invalid_ignored(self):
        rl = RateLimiter(default_rpm=60)
        rl.acquire("p")  # initialize
        rl.update_from_headers("p", {"X-RateLimit-Remaining": "garbage"})
        # Should not raise, and bucket should still work
        assert rl.acquire("p") is True


# ── ResilientProvider ────────────────────────────────────────────────────


class TestResilientProvider:
    """Tests for the composite resilience guard."""

    async def test_should_allow_when_all_ok(self):
        rp = ResilientProvider()
        assert await rp.should_allow("openai") is True

    async def test_should_allow_blocked_by_circuit_breaker(self):
        rp = ResilientProvider()
        # Trip the circuit breaker (default threshold=5)
        for _ in range(5):
            await rp.record_outcome("openai", success=False, latency_ms=100.0)
        assert await rp.should_allow("openai") is False

    async def test_should_allow_blocked_by_rate_limiter(self):
        rl = RateLimiter(default_rpm=1)
        rp = ResilientProvider(rate_limiter=rl)
        assert await rp.should_allow("p") is True
        assert await rp.should_allow("p") is False

    async def test_record_outcome_updates_all_subsystems(self):
        rp = ResilientProvider()
        await rp.record_outcome(
            "openai",
            success=True,
            latency_ms=150.0,
            headers={"X-RateLimit-Remaining": "99"},
        )

        # Health tracker should have the record
        snap = rp.health_tracker.snapshot("openai")
        assert snap.total_requests == 1
        assert snap.rate_limit_remaining == 99

        # Circuit breaker should be closed
        state = await rp.circuit_state("openai")
        assert state.state == "closed"

    async def test_circuit_state_delegates(self):
        rp = ResilientProvider()
        state = await rp.circuit_state("new-provider")
        assert state.state == "closed"
        assert state.failure_count == 0

    async def test_properties_expose_subsystems(self):
        from loom_ai.backends.resilience import CircuitBreakerPolicy

        rp = ResilientProvider()
        assert isinstance(rp.circuit_breaker, CircuitBreakerPolicy)
        assert isinstance(rp.health_tracker, ProviderHealthTracker)
        assert isinstance(rp.rate_limiter, RateLimiter)

    async def test_satisfies_resilience_policy_protocol(self):
        """ResilientProvider satisfies the ResiliencePolicy protocol
        (the core should_allow / record_outcome / circuit_state methods)."""

        rp = ResilientProvider()
        # The protocol requires should_allow, record_outcome, circuit_state.
        # record_outcome has an extra `headers` kwarg but the protocol
        # signature is still satisfied (additional kwargs are fine).
        assert hasattr(rp, "should_allow")
        assert hasattr(rp, "record_outcome")
        assert hasattr(rp, "circuit_state")

    async def test_full_lifecycle(self):
        """Circuit trips after failures, blocks requests, then allows
        after recovery and rate limit check."""
        from loom_ai.backends.resilience import CircuitBreakerPolicy

        cb = CircuitBreakerPolicy(failure_threshold=2, recovery_timeout=0.0)
        rp = ResilientProvider(circuit_breaker=cb)

        # Two failures trip the circuit
        await rp.record_outcome("p", success=False, latency_ms=100.0)
        await rp.record_outcome("p", success=False, latency_ms=100.0)

        state = await rp.circuit_state("p")
        assert state.state == "open"

        # recovery_timeout=0 -> half_open on next check
        assert await rp.should_allow("p") is True  # transitions to half_open

        # Successful probe resets
        await rp.record_outcome("p", success=True, latency_ms=50.0)
        state = await rp.circuit_state("p")
        assert state.state == "closed"

    async def test_headers_forwarded_to_rate_limiter(self):
        rl = RateLimiter(default_rpm=60)
        rp = ResilientProvider(rate_limiter=rl)
        # Initialize bucket
        await rp.should_allow("p")

        await rp.record_outcome(
            "p",
            success=True,
            latency_ms=10.0,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "9999999999.0",
            },
        )
        # Rate limiter should be drained
        assert rl.acquire("p") is False
