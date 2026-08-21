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

from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.prompts import build_arbiter_messages

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
                last_status, last_body = exc.code, {"error": str(exc)}
            if exc.code < 500:
                return last_status, last_body
        except Exception as exc:
            last_status, last_body = 0, {"error": str(exc)}
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))
    return last_status, last_body


async def _async_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = _CHAT_TIMEOUT,
) -> tuple[int, dict]:
    return await asyncio.to_thread(
        _http_request, method, url, headers, body, timeout=timeout
    )


def _openai_chat_body(
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    max_tokens: int | None,
) -> dict:
    msgs = [{"role": m.role, "content": m.content} for m in messages]
    payload: dict = {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    return payload


def _gemini_body(
    messages: list[ChatMessage],
    max_tokens: int | None,
) -> dict:
    contents: list[dict] = []
    system_text: str | None = None
    for m in messages:
        if m.role == "system":
            system_text = m.content
        else:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})
    payload: dict = {"contents": contents}
    if system_text:
        payload["system_instruction"] = {"parts": [{"text": system_text}]}
    if max_tokens is not None:
        payload["generationConfig"] = {"maxOutputTokens": max_tokens}
    return payload


def _parse_openai_response(body: dict, provider: str) -> ChatResponse:
    choice = body.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    return ChatResponse(
        content=content,
        model=body.get("model", ""),
        provider=provider,
        usage=body.get("usage", {}),
    )


def _parse_gemini_response(body: dict, model: str) -> ChatResponse:
    text = ""
    try:
        parts = body["candidates"][0]["content"]["parts"]
        text = parts[-1].get("text", "")
    except (KeyError, IndexError):
        pass
    return ChatResponse(
        content=text,
        model=model,
        provider="gemini",
        usage=body.get("usageMetadata", {}),
    )


def _parse_cohere_response(body: dict) -> ChatResponse:
    text = ""
    try:
        text = body["message"]["content"][0]["text"]
    except (KeyError, IndexError):
        pass
    return ChatResponse(
        content=text,
        model=body.get("model", ""),
        provider="cohere",
        usage=body.get("usage", {}),
    )


class FreeModelRouter:
    """Multi-provider free-tier LLM backend with pluggable selection.

    Satisfies :class:`~loom_ai.protocols.LLMBackend` via structural
    subtyping.  Selection strategy defaults to Thompson Sampling but
    can be swapped at construction time or runtime via
    ``set_strategy()``.
    """

    def __init__(
        self,
        pg_dsn: str = "",
        env_fallback: bool = True,
        strategy: ThompsonSamplingStrategy
        | RoundRobinStrategy
        | LatencyWeightedStrategy
        | CascadeStrategy
        | None = None,
        consensus: bool = True,
        n_workers: int = 3,
    ) -> None:
        self._pg_dsn = pg_dsn or os.environ.get("LOOM_PG_DSN", "")
        self._env_fallback = env_fallback
        self._strategy = strategy or ThompsonSamplingStrategy()
        self._endpoints: list[_ModelEndpoint] = []
        self._initialized = False
        self._consensus = consensus
        self._n_workers = n_workers

    def set_strategy(
        self,
        strategy: ThompsonSamplingStrategy
        | RoundRobinStrategy
        | LatencyWeightedStrategy
        | CascadeStrategy,
    ) -> None:
        self._strategy = strategy

    async def initialize(self) -> None:
        accounts = await self._load_accounts()
        logger.info("Loaded %d provider accounts", len(accounts))

        tasks = [self._probe_account(a) for a in accounts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for acct, result in zip(accounts, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Probe failed for %s/%s: %s",
                    acct.provider,
                    acct.account_name,
                    result,
                )
            elif isinstance(result, list):
                self._endpoints.extend(result)

        self._initialized = True
        logger.info(
            "Discovered %d model endpoints across %d providers",
            len(self._endpoints),
            len({e.provider for e in self._endpoints}),
        )

    async def _load_accounts(self) -> list[_ProviderAccount]:
        accounts: list[_ProviderAccount] = []

        rows = await self._query_secrets()
        for key_name, value in rows:
            provider = _detect_provider(key_name)
            if provider and value:
                accounts.append(
                    _ProviderAccount(
                        provider=provider,
                        api_key=value,
                        account_name=_detect_account(key_name),
                    )
                )

        if self._env_fallback and not accounts:
            for env_key, provider in _KEY_PREFIX_MAP.items():
                val = os.environ.get(f"{env_key}_API_KEY", "")
                if val:
                    accounts.append(
                        _ProviderAccount(
                            provider=provider,
                            api_key=val,
                            account_name="env",
                        )
                    )

        return accounts

    async def _query_secrets(self) -> list[tuple[str, str]]:
        rows = await self._query_secrets_rest()
        if rows:
            return rows
        return await self._query_secrets_psql()

    async def _query_secrets_rest(self) -> list[tuple[str, str]]:
        api_url = os.environ.get(
            "LOOM_SECRETS_API",
            "http://localhost:5000/secrets",
        )
        try:
            status, body = await _async_request(
                "GET",
                api_url,
                {"X-Secret-Access-Reason": "FreeModelRouter discovery"},
                timeout=5,
            )
            if status != 200:
                return []
            key_names = [
                k
                for k in body.get("keys", [])
                if "API_KEY" in k and k.startswith("PERSONAL_")
            ]
            rows: list[tuple[str, str]] = []
            for key_name in key_names:
                try:
                    s, val_body = await _async_request(
                        "GET",
                        f"{api_url}/{key_name}",
                        {"X-Secret-Access-Reason": "FreeModelRouter"},
                        timeout=3,
                    )
                    if s == 200 and val_body.get("value"):
                        rows.append((key_name, val_body["value"]))
                except Exception as exc:
                    logger.debug("Failed to fetch key %s: %s", key_name, exc)
            return rows
        except Exception as exc:
            logger.debug("REST secrets API unavailable: %s", exc)
            return []

    async def _query_secrets_psql(self) -> list[tuple[str, str]]:
        try:
            import subprocess

            result = await asyncio.to_thread(
                subprocess.run,  # NOSONAR — hardcoded psql command, no user input
                [
                    "psql",
                    self._pg_dsn,
                    "-t",
                    "-A",
                    "-F",
                    "\t",
                    "-c",
                    "SELECT key, value FROM auth.secrets "
                    "WHERE encrypted = false "
                    "AND key LIKE 'PERSONAL_%API_KEY%' "
                    "ORDER BY key",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            rows: list[tuple[str, str]] = []
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    rows.append((parts[0], parts[1]))
            return rows
        except Exception as exc:
            logger.warning("Failed to query secrets from PG: %s", exc)
            return []

    async def _probe_account(
        self,
        account: _ProviderAccount,
    ) -> list[_ModelEndpoint]:
        provider = account.provider
        endpoints: list[_ModelEndpoint] = []

        try:
            models = await self._discover_models(provider, account.api_key)
            for model_id in models:
                endpoints.append(
                    _ModelEndpoint(
                        provider=provider,
                        model_id=model_id,
                        api_key=account.api_key,
                        account_name=account.account_name,
                    )
                )
        except Exception as exc:
            logger.debug(
                "Probe failed for %s/%s: %s",
                provider,
                account.account_name,
                exc,
            )

        return endpoints

    async def _discover_models(
        self,
        provider: str,
        api_key: str,
    ) -> list[str]:
        base = _PROVIDER_URLS.get(provider, "")
        if not base:
            return []

        if provider in ("groq", "cerebras", "deepinfra", "nvidia"):
            url = f"{base}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            status, body = await _async_request(
                "GET",
                url,
                headers,
                timeout=_PROBE_TIMEOUT,
            )
            if status == 200:
                return [m["id"] for m in body.get("data", [])]

        elif provider == "openrouter":
            url = f"{base}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            status, body = await _async_request(
                "GET",
                url,
                headers,
                timeout=_PROBE_TIMEOUT,
            )
            if status == 200:
                return [
                    m["id"]
                    for m in body.get("data", [])
                    if m.get("pricing", {}).get("prompt") == "0"
                    and m.get("pricing", {}).get("completion") == "0"
                ]

        elif provider == "gemini":
            url = f"{base}/models"
            headers = {"x-goog-api-key": api_key}
            status, body = await _async_request(
                "GET",
                url,
                headers,
                timeout=_PROBE_TIMEOUT,
            )
            if status == 200:
                return [
                    m["name"].removeprefix("models/")
                    for m in body.get("models", [])
                    if "generateContent" in str(m.get("supportedGenerationMethods", []))
                ]

        elif provider == "cohere":
            return ["command-a-03-2025", "command-r-plus", "command-r"]

        return []

    def _select_endpoint(
        self,
        model: str | None = None,
    ) -> list[_ModelEndpoint]:
        candidates = self._endpoints
        if model:
            exact = [e for e in candidates if e.model_id == model]
            if exact:
                candidates = exact
            else:
                partial = [e for e in candidates if model in e.model_id]
                if partial:
                    candidates = partial

        def _score(ep: _ModelEndpoint) -> float:
            key = f"{ep.provider}/{ep.model_id}/{ep.account_name}"
            return self._strategy.score(
                successes=ep.successes,
                failures=ep.failures,
                model_id=ep.model_id,
                provider=ep.provider,
                endpoint_key=key,
            )

        return sorted(candidates, key=_score, reverse=True)

    def _record(
        self,
        ep: _ModelEndpoint,
        success: bool,
        latency_s: float = 0.0,
    ) -> None:
        if success:
            ep.successes += 1
        else:
            ep.failures += 1
        key = f"{ep.provider}/{ep.model_id}/{ep.account_name}"
        self._strategy.record(
            success=success,
            endpoint_key=key,
            latency_s=latency_s,
        )

    def _select_diverse_workers(self, n: int = 3) -> list[_ModelEndpoint]:
        by_provider: dict[str, list[tuple[float, _ModelEndpoint]]] = {}
        for ep in self._endpoints:
            key = f"{ep.provider}/{ep.model_id}/{ep.account_name}"
            score = self._strategy.score(
                successes=ep.successes,
                failures=ep.failures,
                model_id=ep.model_id,
                provider=ep.provider,
                endpoint_key=key,
            )
            by_provider.setdefault(ep.provider, []).append((score, ep))
        for group in by_provider.values():
            group.sort(key=lambda t: t[0], reverse=True)
        selected: list[_ModelEndpoint] = []
        providers = list(by_provider.keys())
        idx = 0
        while len(selected) < n and providers:
            provider = providers[idx % len(providers)]
            group = by_provider[provider]
            if group:
                selected.append(group.pop(0)[1])
            if not group:
                providers.remove(provider)
                if providers:
                    idx = idx % len(providers)
                continue
            idx += 1
        return selected

    def _select_arbiter(self, exclude_providers: set[str]) -> _ModelEndpoint:
        candidates = [
            ep for ep in self._endpoints if ep.provider not in exclude_providers
        ]
        if not candidates:
            logger.warning("No arbiter outside worker providers; reusing pool")
            candidates = self._endpoints[:]
        return max(
            candidates,
            key=lambda ep: self._strategy.score(
                successes=ep.successes,
                failures=ep.failures,
                model_id=ep.model_id,
                provider=ep.provider,
                endpoint_key=f"{ep.provider}/{ep.model_id}/{ep.account_name}",
            ),
        )

    async def consensus_chat(
        self,
        messages: list[ChatMessage],
        *,
        n_workers: int = 3,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if not self._initialized:
            await self.initialize()
        workers = self._select_diverse_workers(n=n_workers)

        async def _run_worker(
            ep: _ModelEndpoint,
        ) -> tuple[_ModelEndpoint, ChatResponse | None]:
            t0 = time.monotonic()
            try:
                resp = await self._call(ep, messages, temperature, max_tokens)
                self._record(ep, True, time.monotonic() - t0)
                return ep, resp
            except Exception as exc:
                self._record(ep, False, time.monotonic() - t0)
                logger.debug("Worker %s/%s failed: %s", ep.provider, ep.model_id, exc)
                return ep, None

        results = await asyncio.gather(*(_run_worker(ep) for ep in workers))

        worker_dicts: list[dict[str, str]] = []
        successful: list[ChatResponse] = []
        for ep, resp in results:
            if resp is not None and resp.content:
                successful.append(resp)
                worker_dicts.append(
                    {"model": f"{ep.provider}/{ep.model_id}", "response": resp.content}
                )

        if not successful:
            raise RuntimeError("All worker endpoints failed in consensus")

        user_prompt = "\n".join(m.content for m in messages if m.role == "user")
        arbiter_msg_dicts = build_arbiter_messages(user_prompt, worker_dicts)
        arbiter_msgs = [
            ChatMessage(role=d["role"], content=d["content"]) for d in arbiter_msg_dicts
        ]

        worker_providers = {ep.provider for ep, _ in results}
        arbiter_ep = self._select_arbiter(exclude_providers=worker_providers)
        t0 = time.monotonic()
        try:
            arbiter_resp = await self._call(
                arbiter_ep, arbiter_msgs, temperature, max_tokens
            )
            self._record(arbiter_ep, True, time.monotonic() - t0)
            return arbiter_resp
        except Exception as exc:
            self._record(arbiter_ep, False, time.monotonic() - t0)
            logger.warning(
                "Arbiter %s/%s failed: %s",
                arbiter_ep.provider,
                arbiter_ep.model_id,
                exc,
            )
            return successful[0]

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if not self._initialized:
            await self.initialize()

        if (
            self._consensus
            and model is None
            and len(self._endpoints) >= self._n_workers + 1
        ):
            return await self.consensus_chat(
                messages,
                n_workers=self._n_workers,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        candidates = self._select_endpoint(model)
        if not candidates:
            raise RuntimeError("No free model endpoints available")

        last_err: Exception | None = None
        for ep in candidates:
            t0 = time.monotonic()
            try:
                resp = await self._call(ep, messages, temperature, max_tokens)
                if not resp.content:
                    raise RuntimeError("Empty response")
                self._record(ep, True, time.monotonic() - t0)
                return resp
            except Exception as exc:
                self._record(ep, False, time.monotonic() - t0)
                last_err = exc
                logger.debug("Failed %s/%s: %s", ep.provider, ep.model_id, exc)

        raise RuntimeError(f"All {len(candidates)} endpoints failed. Last: {last_err}")

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        resp = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield resp.content

    async def list_models(self) -> list[str]:
        if not self._initialized:
            await self.initialize()
        return sorted({ep.model_id for ep in self._endpoints})

    async def _call(
        self,
        ep: _ModelEndpoint,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> ChatResponse:
        if ep.provider in ("groq", "openrouter", "cerebras", "deepinfra", "nvidia"):
            return await self._call_openai(ep, messages, temperature, max_tokens)
        if ep.provider == "gemini":
            return await self._call_gemini(ep, messages, max_tokens)
        if ep.provider == "cohere":
            return await self._call_cohere(ep, messages, temperature, max_tokens)
        raise RuntimeError(f"Unsupported provider: {ep.provider}")

    async def _call_openai(
        self,
        ep: _ModelEndpoint,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> ChatResponse:
        base = _PROVIDER_URLS[ep.provider]
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {ep.api_key}"}
        body = _openai_chat_body(messages, ep.model_id, temperature, max_tokens)
        status, resp = await _async_request("POST", url, headers, body)
        if status != 200:
            raise RuntimeError(f"HTTP {status}: {resp}")
        return _parse_openai_response(resp, ep.provider)

    async def _call_gemini(
        self,
        ep: _ModelEndpoint,
        messages: list[ChatMessage],
        max_tokens: int | None,
    ) -> ChatResponse:
        base = _PROVIDER_URLS["gemini"]
        url = f"{base}/models/{ep.model_id}:generateContent"
        headers = {"x-goog-api-key": ep.api_key}
        body = _gemini_body(messages, max_tokens)
        status, resp = await _async_request("POST", url, headers, body)
        if status != 200:
            raise RuntimeError(f"Gemini HTTP {status}: {resp}")
        return _parse_gemini_response(resp, ep.model_id)

    async def _call_cohere(
        self,
        ep: _ModelEndpoint,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> ChatResponse:
        url = f"{_PROVIDER_URLS['cohere']}/chat"
        headers = {"Authorization": f"Bearer {ep.api_key}"}
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        body: dict = {
            "model": ep.model_id,
            "messages": msgs,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        status, resp = await _async_request("POST", url, headers, body)
        if status != 200:
            raise RuntimeError(f"Cohere HTTP {status}: {resp}")
        return _parse_cohere_response(resp)

    def stats(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for ep in self._endpoints:
            key = f"{ep.provider}/{ep.model_id}/{ep.account_name}"
            result[key] = {
                "successes": ep.successes,
                "failures": ep.failures,
                "score": (
                    ep.successes / (ep.successes + ep.failures)
                    if (ep.successes + ep.failures) > 0
                    else 0.0
                ),
            }
        return result
