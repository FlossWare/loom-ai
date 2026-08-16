"""Tests for CircuitBreakerPolicy -- closed/open/half_open transitions,
recovery timeout, and success resets.

No external dependencies beyond pytest / pytest-asyncio.
"""

from __future__ import annotations

from unittest.mock import patch

from loom_ai.backends.resilience import CircuitBreakerPolicy

# -- helpers ----------------------------------------------------------------


async def _fail_n(policy: CircuitBreakerPolicy, provider: str, n: int) -> None:
    """Record *n* consecutive failures."""
    for _ in range(n):
        await policy.record_outcome(provider, success=False, latency_ms=100.0)


# -- basic state tests ------------------------------------------------------


async def test_new_provider_starts_closed():
    policy = CircuitBreakerPolicy()
    state = await policy.circuit_state("openai")
    assert state.state == "closed"
    assert state.failure_count == 0
    assert state.last_failure_at == ""
    assert state.next_retry_at == ""


async def test_should_allow_when_closed():
    policy = CircuitBreakerPolicy()
    assert await policy.should_allow("openai") is True


async def test_success_resets_failure_count():
    policy = CircuitBreakerPolicy(failure_threshold=5)
    await _fail_n(policy, "openai", 3)
    state = await policy.circuit_state("openai")
    assert state.failure_count == 3

    await policy.record_outcome("openai", success=True, latency_ms=50.0)
    state = await policy.circuit_state("openai")
    assert state.failure_count == 0
    assert state.state == "closed"


# -- closed -> open transition ----------------------------------------------


async def test_opens_after_threshold_failures():
    policy = CircuitBreakerPolicy(failure_threshold=3)
    await _fail_n(policy, "openai", 3)

    state = await policy.circuit_state("openai")
    assert state.state == "open"
    assert state.failure_count == 3
    assert state.last_failure_at != ""
    assert state.next_retry_at != ""


async def test_should_allow_returns_false_when_open():
    policy = CircuitBreakerPolicy(failure_threshold=2)
    await _fail_n(policy, "openai", 2)

    assert await policy.should_allow("openai") is False


# -- open -> half_open transition (recovery timeout) -------------------------


async def test_transitions_to_half_open_after_timeout():
    policy = CircuitBreakerPolicy(failure_threshold=2, recovery_timeout=10.0)
    await _fail_n(policy, "openai", 2)

    state = await policy.circuit_state("openai")
    assert state.state == "open"

    # Simulate time passing beyond recovery_timeout
    with patch("loom_ai.backends.resilience.time") as mock_time:
        # opened_at was set by the last failure; advance past recovery
        opened_at = policy._providers["openai"].opened_at
        mock_time.time.return_value = opened_at + 11.0
        assert await policy.should_allow("openai") is True

    state = await policy.circuit_state("openai")
    assert state.state == "half_open"


async def test_stays_open_before_timeout():
    policy = CircuitBreakerPolicy(failure_threshold=2, recovery_timeout=60.0)
    await _fail_n(policy, "openai", 2)

    with patch("loom_ai.backends.resilience.time") as mock_time:
        opened_at = policy._providers["openai"].opened_at
        mock_time.time.return_value = opened_at + 30.0  # only half the timeout
        assert await policy.should_allow("openai") is False

    state = await policy.circuit_state("openai")
    assert state.state == "open"


# -- half_open transitions ---------------------------------------------------


async def test_half_open_success_closes_circuit():
    policy = CircuitBreakerPolicy(failure_threshold=2, recovery_timeout=0.0)
    await _fail_n(policy, "openai", 2)

    # recovery_timeout=0 means it transitions to half_open immediately
    assert await policy.should_allow("openai") is True
    state = await policy.circuit_state("openai")
    assert state.state == "half_open"

    await policy.record_outcome("openai", success=True, latency_ms=200.0)
    state = await policy.circuit_state("openai")
    assert state.state == "closed"
    assert state.failure_count == 0


async def test_half_open_failure_reopens_circuit():
    policy = CircuitBreakerPolicy(failure_threshold=2, recovery_timeout=0.0)
    await _fail_n(policy, "openai", 2)

    # Transition to half_open
    assert await policy.should_allow("openai") is True
    state = await policy.circuit_state("openai")
    assert state.state == "half_open"

    await policy.record_outcome("openai", success=False, latency_ms=500.0)
    state = await policy.circuit_state("openai")
    assert state.state == "open"
    assert state.failure_count == 3  # previous 2 + 1 new


# -- provider isolation -----------------------------------------------------


async def test_providers_are_independent():
    policy = CircuitBreakerPolicy(failure_threshold=2)
    await _fail_n(policy, "openai", 2)

    assert await policy.should_allow("openai") is False
    assert await policy.should_allow("anthropic") is True

    state_openai = await policy.circuit_state("openai")
    state_anthropic = await policy.circuit_state("anthropic")
    assert state_openai.state == "open"
    assert state_anthropic.state == "closed"


# -- default parameter values ------------------------------------------------


async def test_default_threshold_is_five():
    policy = CircuitBreakerPolicy()
    await _fail_n(policy, "p", 4)
    state = await policy.circuit_state("p")
    assert state.state == "closed"

    await policy.record_outcome("p", success=False, latency_ms=100.0)
    state = await policy.circuit_state("p")
    assert state.state == "open"


async def test_default_recovery_timeout_is_sixty():
    policy = CircuitBreakerPolicy()
    assert policy._recovery_timeout == 60.0


# -- protocol conformance ---------------------------------------------------


async def test_satisfies_resilience_policy_protocol():
    from loom_ai.contracts_phase2 import ResiliencePolicy

    assert isinstance(CircuitBreakerPolicy(), ResiliencePolicy)


# -- circuit_state timestamps ------------------------------------------------


async def test_circuit_state_timestamps_populated_when_open():
    policy = CircuitBreakerPolicy(failure_threshold=1)
    await policy.record_outcome("openai", success=False, latency_ms=100.0)

    state = await policy.circuit_state("openai")
    assert state.state == "open"
    assert state.last_failure_at != ""
    assert state.next_retry_at != ""
    # ISO format includes "T"
    assert "T" in state.last_failure_at
    assert "T" in state.next_retry_at


async def test_circuit_state_no_next_retry_when_closed():
    policy = CircuitBreakerPolicy()
    await policy.record_outcome("openai", success=False, latency_ms=100.0)

    state = await policy.circuit_state("openai")
    assert state.state == "closed"
    assert state.next_retry_at == ""


# -- full lifecycle ----------------------------------------------------------


async def test_full_lifecycle():
    """closed -> open -> half_open -> closed round trip."""
    policy = CircuitBreakerPolicy(failure_threshold=3, recovery_timeout=0.0)

    # Phase 1: closed, accumulate failures
    for i in range(2):
        assert await policy.should_allow("provider") is True
        await policy.record_outcome("provider", success=False, latency_ms=100.0)

    state = await policy.circuit_state("provider")
    assert state.state == "closed"
    assert state.failure_count == 2

    # Phase 2: one more failure opens the circuit
    await policy.record_outcome("provider", success=False, latency_ms=100.0)
    state = await policy.circuit_state("provider")
    assert state.state == "open"

    # Phase 3: recovery_timeout=0 -> should_allow transitions to half_open
    assert await policy.should_allow("provider") is True
    state = await policy.circuit_state("provider")
    assert state.state == "half_open"

    # Phase 4: success resets to closed
    await policy.record_outcome("provider", success=True, latency_ms=50.0)
    state = await policy.circuit_state("provider")
    assert state.state == "closed"
    assert state.failure_count == 0
