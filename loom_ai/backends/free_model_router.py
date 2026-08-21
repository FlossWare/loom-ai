"""Multi-provider free-tier LLM router.

Discovers available free models across multiple providers and accounts,
auto-falls back on failure, and delegates endpoint ranking to a
pluggable :class:`~loom_ai.protocols.ModelSelectionStrategy`.

Ships four strategies:

* **ThompsonSamplingStrategy** (default) -- Bayesian explore/exploit
* **RoundRobinStrategy** -- even spread across accounts to avoid rate limits
* **LatencyWeightedStrategy** -- prefer faster providers for interactive use
* **CascadeStrategy** -- try preferred models first, fall back to others

Zero external dependencies -- stdlib only (urllib, asyncio, json).

Designed by Gemini 3.6 Flash, reviewed by Cohere Command-A, assembled
by Claude.  Issue #699.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, AsyncIterator

from loom_ai.consensus import ConsensusEngine
from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.prompts import (
    build_arbiter_messages,
    build_worker_messages,
)

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 10
_CHAT_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Concrete selection strategies
# ---------------------------------------------------------------------------


class ThompsonSamplingStrategy:
    """Bayesian exploration/exploitation via Beta-distributed sampling."""

    def score(self, *, successes: int, failures: int, **kwargs: Any) -> float:
        return random.betavariate(successes + 1, failures + 1)

    def record(self, *, success: bool, **kwargs: Any) -> None:
        """Protocol conformance; no per-call state to track."""


class RoundRobinStrategy:
    """Cycle through endpoints evenly to spread rate-limit pressure."""

    def __init__(self) -> None:
        self._counter = 0

    def score(self, *, successes: int, failures: int, **kwargs: Any) -> float:
        _ = successes, failures
        self._counter += 1
        return 1.0 / self._counter

    def record(self, *, success: bool, **kwargs: Any) -> None:
        """Protocol conformance; no per-call state to track."""


class LatencyWeightedStrategy:
    """Prefer endpoints with lower observed latency.

    Falls back to Thompson Sampling when no latency data exists.
    """

    def __init__(self) -> None:
        self._latencies: dict[str, list[float]] = {}

    def score(self, *, successes: int, failures: int, **kwargs: Any) -> float:
        key = kwargs.get("endpoint_key", "")
        samples = self._latencies.get(key, [])
        if not samples:
            return random.betavariate(successes + 1, failures + 1)
        avg = sum(samples[-20:]) / len(samples[-20:])
        return 1.0 / (avg + 0.001)

    def record(self, *, success: bool, **kwargs: Any) -> None:
        _ = success
        key = kwargs.get("endpoint_key", "")
        latency = kwargs.get("latency_s", 0.0)
        if key and latency > 0:
            self._latencies.setdefault(key, []).append(latency)


class CascadeStrategy:
    """Try preferred models first, fall back to everything else.

    Pass ``preferred`` as a list of substrings to match against model
    IDs (e.g. ``["gemini-2.5-flash", "command-a"]``).
    """

    def __init__(self, preferred: list[str] | None = None) -> None:
        self._preferred = preferred or []

    def score(self, *, successes: int, failures: int, **kwargs: Any) -> float:
        model_id = kwargs.get("model_id", "")
        bonus = 100.0 if any(p in model_id for p in self._preferred) else 0.0
        return bonus + random.betavariate(successes + 1, failures + 1)

    def record(self, *, success: bool, **kwargs: Any) -> None:
        """Protocol conformance; no per-call state to track."""


STRATEGIES: dict[str, type] = {
    "thompson": ThompsonSamplingStrategy,
    "round_robin": RoundRobinStrategy,
    "latency": LatencyWeightedStrategy,
    "cascade": CascadeStrategy,
}


# ---------------------------------------------------------------------------
# Internal data classes
# ---------------------------------------------------------------------------


@dataclass
class _ProviderAccount:
    provider: str
    api_key: str
    account_name: str = ""


@dataclass
class _ModelEndpoint:
    provider: str
    model_id: str
    api_key: str
    account_name: str = ""
    successes: int = 0
    failures: int = 0


_PROVIDER_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "cohere": "https://api.cohere.com/v2",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "huggingface": "https://api-inference.huggingface.co",
}

_KEY_PREFIX_MAP: dict[str, str] = {
    "GOOGLE": "gemini",
    "GROQ": "groq",
    "COHERE": "cohere",
    "OPENROUTER": "openrouter",
    "CEREBRAS": "cerebras",
    "DEEPINFRA": "deepinfra",
    "NVIDIA": "nvidia",
    "HUGGINGFACE": "huggingface",
    "CLOUDFLARE": "cloudflare",
}


def _detect_provider(key_name: str) -> str | None:
    upper = key_name.upper()
    for prefix, provider in _KEY_PREFIX_MAP.items():
        if prefix in upper:
            return provider
    return None


def _detect_account(key_name: str) -> str:
    upper = key_name.upper()
    for suffix in ("_FLOSSWARE", "_HOTMAIL", "_NCRR"):
        if upper.endswith(suffix):
            return suffix.lstrip("_").lower()
    return "primary"


def _http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = _CHAT_TIMEOUT,
    retries: int = 2,
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    last_status, last_body = 0, {"error": "no attempts"}
    for attempt in range(1 + retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # NOSONAR — URL from provider config, not user input
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            try:
                last_status, last_body = exc.code, json.loads(exc.read(8192))
            except Exception:
                last_status, last_body = exp.code, {"error": str(exc)}
            if exp.code < 500:
                return last_status, last_body
        except Exception as exc:
            last_status, last_body = 0, {"error": str(exc)}
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))
    return last_status, last_body
