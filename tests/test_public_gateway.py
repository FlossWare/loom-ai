"""Tests for the public free LLM gateway helpers."""

from __future__ import annotations

import os

import pytest


def test_demo_public_enabled(monkeypatch):
    from loom_ai.public_gateway import demo_public_enabled

    monkeypatch.delenv("LOOM_DEMO_PUBLIC", raising=False)
    assert demo_public_enabled() is False
    for val in ("1", "true", "YES", "on"):
        monkeypatch.setenv("LOOM_DEMO_PUBLIC", val)
        assert demo_public_enabled() is True
    monkeypatch.setenv("LOOM_DEMO_PUBLIC", "0")
    assert demo_public_enabled() is False


def test_free_model_allowlist(monkeypatch):
    from loom_ai.public_gateway import free_model_allowlist

    monkeypatch.delenv("LOOM_FREE_MODELS", raising=False)
    assert free_model_allowlist() is None
    monkeypatch.setenv(
        "LOOM_FREE_MODELS",
        "meta-llama/llama-3.3-70b-instruct:free, groq/llama",
    )
    allow = free_model_allowlist()
    assert allow is not None
    assert "meta-llama/llama-3.3-70b-instruct:free" in allow
    assert "groq/llama" in allow


def test_public_rpm_and_cap(monkeypatch):
    from loom_ai.public_gateway import public_max_tokens_cap, public_rpm

    monkeypatch.setenv("LOOM_PUBLIC_RPM", "15")
    assert public_rpm() == 15.0
    monkeypatch.setenv("LOOM_PUBLIC_MAX_TOKENS", "512")
    assert public_max_tokens_cap() == 512


def test_ip_rate_limiter():
    from loom_ai.public_gateway import _IpRateLimiter

    lim = _IpRateLimiter(rpm=2)
    ok, _ = lim.check("1.1.1.1")
    assert ok is True
    ok, _ = lim.check("1.1.1.1")
    assert ok is True
    ok, retry = lim.check("1.1.1.1")
    assert ok is False
    assert retry > 0
    # Different IP is independent
    ok, _ = lim.check("2.2.2.2")
    assert ok is True


def test_require_api_key_demo_bypass():
    from loom_ai.security_bind import require_api_key_for_non_loopback

    # Loopback always ok
    require_api_key_for_non_loopback("127.0.0.1", None)
    # Non-loopback without key fails
    with pytest.raises(SystemExit):
        require_api_key_for_non_loopback("0.0.0.0", None)
    # Demo public allows non-loopback without key
    require_api_key_for_non_loopback("0.0.0.0", None, allow_public_demo=True)
    # Key always allows
    require_api_key_for_non_loopback("0.0.0.0", "secret")
