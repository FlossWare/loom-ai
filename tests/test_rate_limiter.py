"""Tests for RateLimiter -- token-bucket refill, concurrent access,
header parsing, and per-provider isolation.

No external dependencies beyond pytest / pytest-asyncio.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from loom_ai.backends.rate_limiter import (
    ProviderLimits,
    RateLimiter,
    RateLimitInfo,
)

# -- helpers ----------------------------------------------------------------

_MONO_MODULE = "loom_ai.backends.rate_limiter.time"


def _limiter(
    rpm: float = 60.0,
    tpm: float = 0.0,
    **provider_overrides: ProviderLimits,
) -> RateLimiter:
    return RateLimiter(
        default_limits=ProviderLimits(
            requests_per_minute=rpm,
            tokens_per_minute=tpm,
        ),
        provider_limits=provider_overrides or None,
    )


# -- token bucket basics ----------------------------------------------------


async def test_acquire_succeeds_when_bucket_has_capacity():
    limiter = _limiter(rpm=60)
    waited = await limiter.acquire("openai")
    assert waited == 0.0


async def test_bucket_starts_full():
    limiter = _limiter(rpm=10)
    for _ in range(10):
        waited = await limiter.acquire("openai")
        assert waited == 0.0


async def test_acquire_returns_zero_when_limits_disabled():
    limiter = _limiter(rpm=0)
    waited = await limiter.acquire("openai")
    assert waited == 0.0


# -- refill behaviour -------------------------------------------------------


async def test_tokens_refill_over_time():
    limiter = _limiter(rpm=60)
    bucket = limiter._get_request_bucket("openai")

    t0 = 1000.0
    with patch(_MONO_MODULE) as mock_time:
        mock_time.monotonic.return_value = t0
        bucket.tokens = 0.0
        bucket.last_refill = t0

        mock_time.monotonic.return_value = t0 + 1.0
        bucket.refill(mock_time.monotonic())
        assert bucket.tokens == 1.0


async def test_tokens_do_not_exceed_capacity():
    limiter = _limiter(rpm=60)
    bucket = limiter._get_request_bucket("openai")

    t0 = 1000.0
    with patch(_MONO_MODULE) as mock_time:
        mock_time.monotonic.return_value = t0
        bucket.tokens = 59.0
        bucket.last_refill = t0

        mock_time.monotonic.return_value = t0 + 120.0
        bucket.refill(mock_time.monotonic())
        assert bucket.tokens == 60.0


async def test_refill_no_op_for_zero_elapsed():
    limiter = _limiter(rpm=60)
    bucket = limiter._get_request_bucket("openai")

    bucket.tokens = 5.0
    now = bucket.last_refill
    bucket.refill(now)
    assert bucket.tokens == 5.0


# -- acquire waiting -------------------------------------------------------


async def test_acquire_waits_when_empty():
    limiter = _limiter(rpm=600)
    bucket = limiter._get_request_bucket("openai")

    async with bucket.lock:
        bucket.tokens = 0.0

    waited = await limiter.acquire("openai")
    assert waited >= 0.0


# -- token-rate limiting ----------------------------------------------------


async def test_token_bucket_deduction():
    limiter = _limiter(rpm=60, tpm=1000)
    waited = await limiter.acquire("openai", tokens=100)
    assert waited == 0.0

    bucket = limiter._get_token_bucket("openai")
    assert bucket.tokens < 1000.0


async def test_record_tokens_deducts_from_bucket():
    limiter = _limiter(rpm=60, tpm=1000)
    limiter._get_token_bucket("openai")
    await limiter.record_tokens("openai", 200)

    bucket = limiter._get_token_bucket("openai")
    assert bucket.tokens <= 800.0


async def test_record_tokens_noop_when_disabled():
    limiter = _limiter(rpm=60, tpm=0)
    await limiter.record_tokens("openai", 500)
    assert "openai" not in limiter._token_buckets


async def test_record_tokens_noop_for_zero():
    limiter = _limiter(rpm=60, tpm=1000)
    await limiter.record_tokens("openai", 0)
    assert "openai" not in limiter._token_buckets


# -- header parsing ---------------------------------------------------------


async def test_parse_all_headers():
    headers = {
        "X-RateLimit-Remaining": "42",
        "X-RateLimit-Reset": "1700000000.0",
        "Retry-After": "5.5",
    }
    info = RateLimiter.parse_headers(headers)
    assert info.remaining == 42
    assert info.reset_at == 1700000000.0
    assert info.retry_after == 5.5


async def test_parse_headers_case_insensitive():
    headers = {
        "x-ratelimit-remaining": "10",
        "retry-after": "3",
    }
    info = RateLimiter.parse_headers(headers)
    assert info.remaining == 10
    assert info.retry_after == 3.0


async def test_parse_headers_missing_values():
    info = RateLimiter.parse_headers({})
    assert info.remaining is None
    assert info.reset_at is None
    assert info.retry_after is None


async def test_parse_headers_invalid_values():
    headers = {
        "X-RateLimit-Remaining": "not-a-number",
        "X-RateLimit-Reset": "bad",
        "Retry-After": "nope",
    }
    info = RateLimiter.parse_headers(headers)
    assert info.remaining is None
    assert info.reset_at is None
    assert info.retry_after is None


async def test_parse_headers_partial():
    headers = {"X-RateLimit-Remaining": "5"}
    info = RateLimiter.parse_headers(headers)
    assert info.remaining == 5
    assert info.reset_at is None
    assert info.retry_after is None


# -- update_from_headers ----------------------------------------------------


async def test_update_from_headers_sets_remaining():
    limiter = _limiter(rpm=60)
    info = RateLimitInfo(remaining=3)
    await limiter.update_from_headers("openai", info)

    bucket = limiter._get_request_bucket("openai")
    assert bucket.tokens == 3.0


async def test_update_from_headers_remaining_capped_at_capacity():
    limiter = _limiter(rpm=10)
    info = RateLimitInfo(remaining=999)
    await limiter.update_from_headers("openai", info)

    bucket = limiter._get_request_bucket("openai")
    assert bucket.tokens == 10.0


async def test_update_from_headers_retry_after_drains_bucket():
    limiter = _limiter(rpm=60)
    info = RateLimitInfo(retry_after=30.0)
    await limiter.update_from_headers("openai", info)

    bucket = limiter._get_request_bucket("openai")
    assert bucket.tokens == 0.0


async def test_update_from_headers_no_effect_when_empty():
    limiter = _limiter(rpm=60)
    bucket = limiter._get_request_bucket("openai")
    original = bucket.tokens

    info = RateLimitInfo()
    await limiter.update_from_headers("openai", info)
    assert bucket.tokens == original


# -- per-provider isolation --------------------------------------------------


async def test_providers_have_independent_buckets():
    limiter = _limiter(rpm=2)

    await limiter.acquire("openai")
    await limiter.acquire("openai")

    bucket_openai = limiter._get_request_bucket("openai")
    bucket_anthropic = limiter._get_request_bucket("anthropic")

    assert bucket_openai.tokens < 0.01
    assert bucket_anthropic.tokens == 2.0


async def test_provider_specific_limits():
    limiter = RateLimiter(
        default_limits=ProviderLimits(requests_per_minute=60),
        provider_limits={
            "openai": ProviderLimits(requests_per_minute=10),
            "anthropic": ProviderLimits(requests_per_minute=100),
        },
    )

    bucket_openai = limiter._get_request_bucket("openai")
    bucket_anthropic = limiter._get_request_bucket("anthropic")
    bucket_other = limiter._get_request_bucket("groq")

    assert bucket_openai.capacity == 10.0
    assert bucket_anthropic.capacity == 100.0
    assert bucket_other.capacity == 60.0


async def test_update_headers_isolated_per_provider():
    limiter = _limiter(rpm=60)
    await limiter.update_from_headers("openai", RateLimitInfo(remaining=1))

    bucket_openai = limiter._get_request_bucket("openai")
    bucket_anthropic = limiter._get_request_bucket("anthropic")

    assert bucket_openai.tokens == 1.0
    assert bucket_anthropic.tokens == 60.0


# -- concurrent access -------------------------------------------------------


async def test_concurrent_acquires_respect_capacity():
    limiter = _limiter(rpm=5)

    results = await asyncio.gather(*[limiter.acquire("openai") for _ in range(5)])
    assert all(w == 0.0 for w in results)

    bucket = limiter._get_request_bucket("openai")
    assert bucket.tokens < 0.01


async def test_concurrent_acquires_across_providers():
    limiter = _limiter(rpm=3)

    tasks = [
        limiter.acquire("openai"),
        limiter.acquire("anthropic"),
        limiter.acquire("openai"),
        limiter.acquire("anthropic"),
    ]
    results = await asyncio.gather(*tasks)
    assert all(isinstance(w, float) for w in results)


async def test_concurrent_record_tokens():
    limiter = _limiter(rpm=60, tpm=10000)
    limiter._get_token_bucket("openai")

    await asyncio.gather(*[limiter.record_tokens("openai", 100) for _ in range(10)])

    bucket = limiter._get_token_bucket("openai")
    assert bucket.tokens <= 9001.0


# -- dataclass defaults ------------------------------------------------------


async def test_provider_limits_defaults():
    limits = ProviderLimits()
    assert limits.requests_per_minute == 60.0
    assert limits.tokens_per_minute == 0.0


async def test_rate_limit_info_defaults():
    info = RateLimitInfo()
    assert info.remaining is None
    assert info.reset_at is None
    assert info.retry_after is None


# -- edge cases --------------------------------------------------------------


async def test_acquire_with_zero_rpm_skips_request_bucket():
    limiter = _limiter(rpm=0, tpm=1000)
    waited = await limiter.acquire("openai", tokens=50)
    assert waited == 0.0
    assert "openai" not in limiter._request_buckets


async def test_acquire_with_zero_tokens_skips_token_bucket():
    limiter = _limiter(rpm=60, tpm=1000)
    waited = await limiter.acquire("openai", tokens=0)
    assert waited == 0.0
    assert "openai" not in limiter._token_buckets


async def test_multiple_providers_default_limits():
    limiter = _limiter(rpm=30)
    for name in ["openai", "anthropic", "groq", "deepseek"]:
        waited = await limiter.acquire(name)
        assert waited == 0.0
        bucket = limiter._get_request_bucket(name)
        assert bucket.capacity == 30.0
