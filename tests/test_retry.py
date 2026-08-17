"""Tests for the reusable async retry module (#294).

Covers exponential backoff, max-retries exhaustion, non-retryable exception
classification, circuit-breaker integration, and jitter randomisation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom_ai.backends.resilience import CircuitBreakerPolicy
from loom_ai.backends.retry import (
    CircuitOpenError,
    RetriesExhaustedError,
    RetryPolicy,
    async_retry,
)

# ── RetryPolicy unit tests ─────────────────────────────────────────


def test_default_policy_values():
    policy = RetryPolicy()
    assert policy.max_retries == 3
    assert policy.backoff_base == 2.0
    assert policy.backoff_cap == 10.0
    assert policy.jitter_range == 1.0
    assert policy.retry_on == ()
    assert policy.no_retry_on == ()


def test_is_retryable_default_retries_all():
    policy = RetryPolicy()
    assert policy.is_retryable(ValueError("oops")) is True
    assert policy.is_retryable(RuntimeError("oops")) is True
    assert policy.is_retryable(OSError("oops")) is True


def test_is_retryable_respects_retry_on():
    policy = RetryPolicy(retry_on=(ConnectionError, TimeoutError))
    assert policy.is_retryable(ConnectionError()) is True
    assert policy.is_retryable(TimeoutError()) is True
    assert policy.is_retryable(ValueError()) is False


def test_is_retryable_no_retry_on_takes_precedence():
    policy = RetryPolicy(
        retry_on=(Exception,),
        no_retry_on=(ValueError,),
    )
    assert policy.is_retryable(ValueError("fatal")) is False
    assert policy.is_retryable(RuntimeError("transient")) is True


def test_delay_exponential_backoff():
    policy = RetryPolicy(backoff_base=2.0, jitter_range=0.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)

    assert policy.delay(0) == 1.0  # 2^0 = 1
    assert policy.delay(1) == 2.0  # 2^1 = 2
    assert policy.delay(2) == 4.0  # 2^2 = 4
    assert policy.delay(3) == 8.0  # 2^3 = 8


def test_delay_capped_at_backoff_cap():
    policy = RetryPolicy(backoff_base=2.0, backoff_cap=5.0, jitter_range=0.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)

    assert policy.delay(10) == 5.0  # 2^10 = 1024, capped to 5.0


def test_delay_includes_jitter():
    policy = RetryPolicy(backoff_base=2.0, jitter_range=1.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.75)

    # 2^0 + 0.75 = 1.75
    assert policy.delay(0) == 1.75


# ── async_retry decorator tests ────────────────────────────────────


async def test_success_no_retry():
    call_count = 0

    @async_retry(RetryPolicy(max_retries=3))
    async def succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await succeed()
    assert result == "ok"
    assert call_count == 1


async def test_retry_then_succeed():
    call_count = 0
    policy = RetryPolicy(max_retries=3, jitter_range=0.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)

    @async_retry(policy)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient")
        return "recovered"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await flaky()

    assert result == "recovered"
    assert call_count == 3
    assert mock_sleep.call_count == 2


async def test_exponential_backoff_delays():
    call_count = 0
    policy = RetryPolicy(max_retries=3, backoff_base=2.0, jitter_range=0.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)

    @async_retry(policy)
    async def fail_twice():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("boom")
        return "done"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await fail_twice()

    assert result == "done"
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_await(1.0)  # 2^0
    mock_sleep.assert_any_await(2.0)  # 2^1


async def test_max_retries_exhausted():
    policy = RetryPolicy(max_retries=2, jitter_range=0.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)
    call_count = 0

    @async_retry(policy)
    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("persistent")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RetriesExhaustedError) as exc_info:
            await always_fail()

    err = exc_info.value
    assert err.attempts == 3  # max_retries(2) + 1
    assert isinstance(err.last_exception, RuntimeError)
    assert "persistent" in str(err.last_exception)
    assert call_count == 3


async def test_non_retryable_exception_skips_retry():
    policy = RetryPolicy(
        max_retries=5,
        no_retry_on=(ValueError,),
    )
    call_count = 0

    @async_retry(policy)
    async def fatal():
        nonlocal call_count
        call_count += 1
        raise ValueError("not retryable")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(ValueError, match="not retryable"):
            await fatal()

    assert call_count == 1
    mock_sleep.assert_not_awaited()


async def test_retry_on_filter():
    policy = RetryPolicy(
        max_retries=5,
        retry_on=(ConnectionError,),
        jitter_range=0.0,
    )
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)
    call_count = 0

    @async_retry(policy)
    async def wrong_error():
        nonlocal call_count
        call_count += 1
        raise TypeError("not in retry_on")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(TypeError, match="not in retry_on"):
            await wrong_error()

    assert call_count == 1
    mock_sleep.assert_not_awaited()


async def test_backoff_cap_respected():
    policy = RetryPolicy(
        max_retries=1,
        backoff_base=2.0,
        backoff_cap=3.0,
    )
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=100.0)
    call_count = 0

    @async_retry(policy)
    async def fail_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("once")
        return "ok"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await fail_once()

    assert result == "ok"
    mock_sleep.assert_awaited_once_with(3.0)


# ── jitter randomisation ───────────────────────────────────────────


def test_jitter_uses_rng_uniform():
    policy = RetryPolicy(jitter_range=2.5)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=1.23)

    delay = policy.delay(0)
    policy._rng.uniform.assert_called_once_with(0, 2.5)
    assert delay == 2.0**0 + 1.23  # 1 + 1.23 = 2.23


def test_different_rng_seeds_produce_different_jitter():
    policy_a = RetryPolicy(jitter_range=1.0)
    policy_a._rng.seed(42)
    policy_b = RetryPolicy(jitter_range=1.0)
    policy_b._rng.seed(99)

    delays_a = [policy_a.delay(i) for i in range(5)]
    delays_b = [policy_b.delay(i) for i in range(5)]
    assert delays_a != delays_b


# ── circuit-breaker integration ────────────────────────────────────


async def test_circuit_open_skips_call():
    cb = CircuitBreakerPolicy(failure_threshold=1)
    await cb.record_outcome("test-provider", success=False, latency_ms=100.0)

    state = await cb.circuit_state("test-provider")
    assert state.state == "open"

    call_count = 0

    @async_retry(RetryPolicy(), resilience=cb, provider="test-provider")
    async def guarded():
        nonlocal call_count
        call_count += 1
        return "should not reach"

    with pytest.raises(CircuitOpenError, match="test-provider"):
        await guarded()

    assert call_count == 0


async def test_circuit_records_success():
    cb = CircuitBreakerPolicy(failure_threshold=5)

    @async_retry(RetryPolicy(), resilience=cb, provider="my-provider")
    async def ok():
        return "done"

    await ok()

    state = await cb.circuit_state("my-provider")
    assert state.state == "closed"
    assert state.failure_count == 0


async def test_circuit_records_failure_on_exhaustion():
    policy = RetryPolicy(max_retries=1, jitter_range=0.0)
    policy._rng = MagicMock()
    policy._rng.uniform = MagicMock(return_value=0.0)
    cb = CircuitBreakerPolicy(failure_threshold=5)

    @async_retry(policy, resilience=cb, provider="failing-provider")
    async def always_fail():
        raise RuntimeError("boom")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RetriesExhaustedError):
            await always_fail()

    state = await cb.circuit_state("failing-provider")
    assert state.failure_count == 1


async def test_circuit_records_failure_on_non_retryable():
    policy = RetryPolicy(no_retry_on=(ValueError,))
    cb = CircuitBreakerPolicy(failure_threshold=5)

    @async_retry(policy, resilience=cb, provider="val-provider")
    async def fatal():
        raise ValueError("fatal")

    with pytest.raises(ValueError):
        await fatal()

    state = await cb.circuit_state("val-provider")
    assert state.failure_count == 1


async def test_circuit_half_open_allows_probe():
    cb = CircuitBreakerPolicy(failure_threshold=1, recovery_timeout=0.0)
    await cb.record_outcome("probe-provider", success=False, latency_ms=100.0)

    @async_retry(RetryPolicy(), resilience=cb, provider="probe-provider")
    async def probe():
        return "probed"

    result = await probe()
    assert result == "probed"

    state = await cb.circuit_state("probe-provider")
    assert state.state == "closed"


# ── decorator preserves function metadata ──────────────────────────


async def test_wraps_preserves_name():
    @async_retry(RetryPolicy())
    async def my_function():
        """My docstring."""
        return 42

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "My docstring."


# ── default policy when None ───────────────────────────────────────


async def test_none_policy_uses_defaults():
    call_count = 0

    @async_retry(None)
    async def succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await succeed()
    assert result == "ok"
    assert call_count == 1
