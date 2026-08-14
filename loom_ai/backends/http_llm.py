"""HTTP-based LLM backend using only stdlib (urllib + asyncio).

Compatible with any OpenAI-compatible ``/chat/completions`` endpoint
including OpenRouter, LiteLLM, vLLM, Ollama, and direct provider APIs.

Zero external dependencies -- no requests, no httpx, no aiohttp.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.request
from typing import AsyncIterator

from loom_ai.models import ChatMessage, ChatResponse


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
        self._ssl_ctx = ssl.create_default_context()

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
    def _parse_response(
        data: dict, model: str, provider: str
    ) -> ChatResponse:
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
        req = self._build_request(
            messages, resolved, temperature, max_tokens
        )

        def _do_request() -> ChatResponse:
            try:
                with urllib.request.urlopen(
                    req, timeout=self._timeout, context=self._ssl_ctx
                ) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)
                    return self._parse_response(
                        data, resolved, self._provider_name
                    )
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")[
                    :1000
                ]
                raise RuntimeError(
                    f"LLM API error {exc.code} from "
                    f"{self._base_url}: {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"LLM API connection error to "
                    f"{self._base_url}: {exc.reason}"
                ) from exc

        return await asyncio.get_running_loop().run_in_executor(
            None, _do_request
        )

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

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _stream_reader() -> None:
            try:
                with urllib.request.urlopen(
                    req, timeout=self._timeout, context=self._ssl_ctx
                ) as resp:
                    for raw_line in resp:
                        line = raw_line.decode(
                            "utf-8", errors="replace"
                        ).rstrip("\n\r")

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
                            loop.call_soon_threadsafe(
                                queue.put_nowait, content
                            )
            except Exception:
                # Stream ends; the sentinel below signals the consumer.
                pass
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _stream_reader)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    async def list_models(self) -> list[str]:
        """Fetch available models from the ``/models`` endpoint."""
        url = f"{self._base_url}/models"
        req = urllib.request.Request(
            url, headers=self._headers(), method="GET"
        )

        def _do_request() -> list[str]:
            try:
                with urllib.request.urlopen(
                    req, timeout=self._timeout, context=self._ssl_ctx
                ) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)
                    models_list = data.get("data", [])
                    return sorted(m["id"] for m in models_list if "id" in m)
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")[
                    :500
                ]
                raise RuntimeError(
                    f"Failed to list models from "
                    f"{self._base_url}: {exc.code} {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Cannot reach {self._base_url}/models: {exc.reason}"
                ) from exc

        return await asyncio.get_running_loop().run_in_executor(
            None, _do_request
        )

    async def consensus(
        self,
        messages: list[ChatMessage],
        models: list[str],
        *,
        temperature: float = 0.7,
        max_concurrent: int = 10,
        timeout_seconds: int = 60,
        retries: int = 2,
    ) -> list[ChatResponse]:
        """Query multiple models concurrently with deadline-based timeouts.

        Uses a semaphore to cap concurrency, exponential backoff with
        jitter on retryable errors (429, 5xx, timeouts), and a per-model
        deadline so slow models don't block the fleet.

        Adapted from the crush MCP consensus server (PR #2).
        """
        import random
        import time

        semaphore = asyncio.Semaphore(max_concurrent)
        deadline = time.monotonic() + timeout_seconds

        async def _worker(model_id: str) -> ChatResponse | None:
            for attempt in range(1 + retries):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    async with semaphore:
                        return await asyncio.wait_for(
                            self.chat(
                                messages,
                                model=model_id,
                                temperature=temperature,
                            ),
                            timeout=remaining,
                        )
                except Exception as exc:
                    if not self._is_retryable(exc):
                        break
                    delay = min(
                        (2 ** attempt) + random.uniform(0, 1),
                        max(0, deadline - time.monotonic()),
                    )
                    if attempt < retries and delay > 0:
                        await asyncio.sleep(delay)
            return None

        tasks = [_worker(m) for m in models]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, asyncio.TimeoutError):
            return True
        if isinstance(exc, RuntimeError):
            msg = str(exc)
            for code in ("429", "500", "502", "503", "504"):
                if code in msg:
                    return True
        return False
