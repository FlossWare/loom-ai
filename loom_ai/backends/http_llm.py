"""HTTP-based LLM backend using only stdlib (urllib + asyncio).

Compatible with any OpenAI-compatible ``/chat/completions`` endpoint
including OpenRouter, LiteLLM, vLLM, Ollama, and direct provider APIs.

Zero external dependencies -- no requests, no httpx, no aiohttp.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
import time
import urllib.error
import urllib.request
from typing import AsyncIterator

from loom_ai.models import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

_RETRY_MAX = 3  # 3 retries → 4 total attempts
_RETRY_BACKOFF_CAP = 10.0  # seconds — max delay between retries


class HttpLLMBackend:
    """OpenAI-compatible chat-completions backend using only stdlib.

    Satisfies :class:`~loom_ai.protocols.LLMBackend` via structural
    subtyping.

    Parameters
    ----------
    base_url:
        Root URL of the OpenAI-compatible API (e.g.
        ``"https://openrouter.ai/api/v1"``).
    api_key:
        Bearer token for the ``Authorization`` header.
        Pass ``""`` for unauthenticated local servers.
    default_model:
        Model id used when callers pass ``model=None``.
    timeout:
        HTTP timeout in seconds for non-streaming requests.
    provider_name:
        Human-readable provider label included in ``ChatResponse``.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        default_model: str = "gpt-4o-mini",
        timeout: int = 120,
        provider_name: str = "openai-compatible",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout
        self._provider_name = provider_name
        self._ssl_ctx = ssl.create_default_context()  # NOSONAR — TLS 1.2 enforced below
        self._ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self._rng = random.Random()  # noqa: S311

    # ── internal helpers ─────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _resolve_model(self, model: str | None) -> str:
        return model if model is not None else self._default_model

    @staticmethod
    def _format_messages(
        messages: list[ChatMessage],
    ) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _build_request(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int | None,
        *,
        stream: bool = False,
    ) -> urllib.request.Request:
        url = f"{self._base_url}/chat/completions"

        payload: dict = {
            "model": model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        body = json.dumps(payload).encode("utf-8")
        return urllib.request.Request(
            url, data=body, headers=self._headers(), method="POST"
        )

    @staticmethod
    def _is_retryable_status(code: int) -> bool:
        """Return *True* for HTTP status codes that warrant a retry."""
        return code == 429 or code >= 500

    @staticmethod
    def _parse_response(data: dict, model: str, provider: str) -> ChatResponse:
        choices = data.get("choices", [])
        content = ""
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")

        usage_raw = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_raw.get("prompt_tokens", 0),
            "completion_tokens": usage_raw.get("completion_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
        }

        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider=provider,
            usage=usage,
        )

    # ── LLMBackend interface ─────────────────────────────────────────

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Send a chat completion request (run in a thread to stay async)."""
        resolved = self._resolve_model(model)
        req = self._build_request(messages, resolved, temperature, max_tokens)

        def _do_request() -> ChatResponse:
            last_exc: Exception | None = None
            for attempt in range(_RETRY_MAX + 1):
                try:
                    with urllib.request.urlopen(  # noqa: S310  # NOSONAR — URL is from constructor config, not user input
                        req, timeout=self._timeout, context=self._ssl_ctx
                    ) as resp:
                        body = resp.read().decode("utf-8")
                        data = json.loads(body)
                        return self._parse_response(data, resolved, self._provider_name)
                except urllib.error.HTTPError as exc:
                    error_body = exc.read().decode("utf-8", errors="replace")[:1000]
                    if not self._is_retryable_status(exc.code):
                        logger.warning(
                            "LLM API error %d from %s: %s",
                            exc.code,
                            self._base_url,
                            error_body,
                        )
                        raise RuntimeError(
                            f"LLM API error {exc.code} from {self._base_url}"
                        ) from exc
                    logger.warning(
                        "LLM API error %d from %s (attempt %d/%d): %s",
                        exc.code,
                        self._base_url,
                        attempt + 1,
                        _RETRY_MAX + 1,
                        error_body,
                    )
                    last_exc = exc
                except urllib.error.URLError as exc:
                    logger.warning(
                        "LLM API connection error to %s (attempt %d/%d): %s",
                        self._base_url,
                        attempt + 1,
                        _RETRY_MAX + 1,
                        exc.reason,
                    )
                    last_exc = exc

                if attempt < _RETRY_MAX:
                    delay = min(
                        2**attempt + self._rng.uniform(0, 1),
                        _RETRY_BACKOFF_CAP,
                    )
                    time.sleep(delay)

            # All retries exhausted — raise with original exception as cause
            if isinstance(last_exc, urllib.error.HTTPError):
                raise RuntimeError(
                    f"LLM API error {last_exc.code} from {self._base_url}"
                ) from last_exc
            if isinstance(last_exc, urllib.error.URLError):
                raise RuntimeError(
                    f"LLM API connection error to {self._base_url}: {last_exc.reason}"
                ) from last_exc
            raise RuntimeError(f"LLM API error: {last_exc}") from last_exc

        return await asyncio.get_running_loop().run_in_executor(None, _do_request)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completions via SSE, yielding content deltas.

        The HTTP response is read line-by-line in a background thread;
        content deltas are fed into an ``asyncio.Queue`` that the caller
        consumes asynchronously.
        """
        resolved = self._resolve_model(model)
        req = self._build_request(
            messages, resolved, temperature, max_tokens, stream=True
        )

        queue: asyncio.Queue[str | None | BaseException] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _stream_reader() -> None:
            try:
                # ── Retry loop for connection establishment ──────────
                last_exc: Exception | None = None
                resp = None
                for attempt in range(_RETRY_MAX + 1):
                    try:
                        resp = urllib.request.urlopen(  # noqa: S310  # NOSONAR — URL is from constructor config, not user input
                            req, timeout=self._timeout, context=self._ssl_ctx
                        )
                        break
                    except urllib.error.HTTPError as exc:
                        error_body = exc.read().decode("utf-8", errors="replace")[:1000]
                        if not self._is_retryable_status(exc.code):
                            logger.warning(
                                "LLM streaming error %d from %s: %s",
                                exc.code,
                                self._base_url,
                                error_body,
                            )
                            error = RuntimeError(
                                f"LLM streaming error {exc.code} from {self._base_url}"
                            )
                            error.__cause__ = exc
                            loop.call_soon_threadsafe(queue.put_nowait, error)
                            return
                        logger.warning(
                            "LLM streaming error %d from %s (attempt %d/%d): %s",
                            exc.code,
                            self._base_url,
                            attempt + 1,
                            _RETRY_MAX + 1,
                            error_body,
                        )
                        last_exc = exc
                    except urllib.error.URLError as exc:
                        logger.warning(
                            "LLM streaming connection error to %s (attempt %d/%d): %s",
                            self._base_url,
                            attempt + 1,
                            _RETRY_MAX + 1,
                            exc.reason,
                        )
                        last_exc = exc
                    except Exception as exc:
                        error = RuntimeError(f"LLM streaming error: {exc}")
                        error.__cause__ = exc
                        loop.call_soon_threadsafe(queue.put_nowait, error)
                        return

                    if attempt < _RETRY_MAX:
                        delay = min(
                            2**attempt + self._rng.uniform(0, 1),
                            _RETRY_BACKOFF_CAP,
                        )
                        time.sleep(delay)

                if resp is None:
                    # All retries exhausted
                    if isinstance(last_exc, urllib.error.HTTPError):
                        error = RuntimeError(
                            f"LLM streaming error {last_exc.code} from {self._base_url}"
                        )
                    elif isinstance(last_exc, urllib.error.URLError):
                        error = RuntimeError(
                            f"LLM streaming connection error to "
                            f"{self._base_url}: {last_exc.reason}"
                        )
                    else:
                        error = RuntimeError(f"LLM streaming error: {last_exc}")
                    error.__cause__ = last_exc
                    loop.call_soon_threadsafe(queue.put_nowait, error)
                    return

                # ── Read SSE chunks from established connection ─────
                try:
                    with resp:
                        for raw_line in resp:
                            line = raw_line.decode("utf-8", errors="replace").rstrip(
                                "\n\r"
                            )

                            if not line.startswith("data: "):
                                continue

                            payload = line[6:]  # strip "data: " prefix
                            if payload.strip() == "[DONE]":
                                break

                            try:
                                chunk = json.loads(payload)
                            except json.JSONDecodeError:
                                continue

                            choices = chunk.get("choices", [])
                            if not choices:
                                continue

                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                loop.call_soon_threadsafe(queue.put_nowait, content)
                except urllib.error.HTTPError as exc:
                    error_body = exc.read().decode("utf-8", errors="replace")[:1000]
                    logger.warning(
                        "LLM streaming error %d from %s: %s",
                        exc.code,
                        self._base_url,
                        error_body,
                    )
                    error = RuntimeError(
                        f"LLM streaming error {exc.code} from {self._base_url}"
                    )
                    error.__cause__ = exc
                    loop.call_soon_threadsafe(queue.put_nowait, error)
                except urllib.error.URLError as exc:
                    error = RuntimeError(
                        f"LLM streaming connection error to "
                        f"{self._base_url}: {exc.reason}"
                    )
                    error.__cause__ = exc
                    loop.call_soon_threadsafe(queue.put_nowait, error)
                except Exception as exc:
                    error = RuntimeError(f"LLM streaming error: {exc}")
                    error.__cause__ = exc
                    loop.call_soon_threadsafe(queue.put_nowait, error)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _stream_reader)

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item

    async def list_models(self) -> list[str]:
        """Fetch available models from the ``/models`` endpoint."""
        url = f"{self._base_url}/models"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")

        def _do_request() -> list[str]:
            try:
                with urllib.request.urlopen(  # noqa: S310  # NOSONAR — URL is from constructor config, not user input
                    req, timeout=self._timeout, context=self._ssl_ctx
                ) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)
                    models_list = data.get("data", [])
                    return sorted(m["id"] for m in models_list if "id" in m)
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")[:500]
                logger.warning(
                    "Failed to list models from %s: %d %s",
                    self._base_url,
                    exc.code,
                    error_body,
                )
                raise RuntimeError(
                    f"Failed to list models from {self._base_url}: {exc.code}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Cannot reach {self._base_url}/models: {exc.reason}"
                ) from exc

        return await asyncio.get_running_loop().run_in_executor(None, _do_request)
