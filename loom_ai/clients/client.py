"""Async SDK client for the loom-ai REST API.

Zero external dependencies -- uses only stdlib (urllib + asyncio).
Wraps every loom-ai REST endpoint with typed Python methods.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    """Connection settings for a loom-ai server."""

    base_url: str = "http://127.0.0.1:5000"
    api_key: str = ""
    timeout: int = 60

    @classmethod
    def from_env(cls) -> ClientConfig:
        try:
            timeout = int(os.environ.get("LOOM_TIMEOUT", "60"))
        except ValueError:
            timeout = 60
        return cls(
            base_url=os.environ.get(
                "LOOM_URL",
                "http://{}:{}".format(  # NOSONAR — loopback default
                    os.environ.get("LOOM_HOST", "127.0.0.1"),
                    os.environ.get("LOOM_PORT", "5000"),
                ),
            ),
            api_key=os.environ.get("LOOM_API_KEY", ""),
            timeout=timeout,
        )


class LoomClient:
    """Async client for the loom-ai REST API.

    All methods are async and use stdlib urllib via asyncio's thread
    executor to avoid blocking the event loop.

    Usage::

        client = LoomClient.from_env()
        response = await client.chat([{"role": "user", "content": "Hello"}])
        print(response["content"])
    """

    def __init__(self, config: ClientConfig | None = None) -> None:
        self._config = config or ClientConfig.from_env()
        self._base = self._config.base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> LoomClient:
        return cls(ClientConfig.from_env())

    @property
    def base_url(self) -> str:
        return self._base

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "loom-ai-client/1.0 (Python)",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        if params:
            qs = "&".join(
                f"{k}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
                if v is not None
            )
            if qs:
                url = f"{url}?{qs}"

        data = json.dumps(body).encode() if body is not None else None
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        def _do() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                    raw = resp.read()
                    if not raw:
                        return {}
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                error_body = exc.read(1024 * 64).decode(errors="replace")
                logger.exception(
                    "HTTP %d from %s: %s",
                    exc.code,
                    url,
                    error_body,
                )
                raise RuntimeError(
                    f"loom-ai API error {exc.code}: {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"loom-ai connection failed: {exc.reason}") from exc
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"loom-ai returned invalid JSON: {exc}") from exc

        return await asyncio.to_thread(_do)

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        filtered = {k: v for k, v in params.items() if v is not None}
        return await self._request("GET", path, params=filtered)

    async def _post(
        self, path: str, body: dict | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        return await self._request("POST", path, body=body, **kwargs)

    # ── Health ───────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        return await self._get("/health")

    async def ready(self) -> dict[str, Any]:
        return await self._get("/ready")

    # ── LLM ──────────────────────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        resp = await self._get("/llm/models")
        return resp.get("models", [])

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
        }
        if model:
            body["model"] = model
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return await self._post("/llm/chat", body)

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        body: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if model:
            body["model"] = model
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        url = f"{self._base}/llm/chat"
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, headers=self._headers(), method="POST"
        )

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        error_holder: list[BaseException] = []
        loop = asyncio.get_running_loop()

        def _stream() -> None:
            try:
                with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                    for raw_line in resp:
                        line = raw_line.decode(errors="replace").strip()
                        if line.startswith("data: "):
                            payload = line[6:]
                            if payload == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload)
                                choice = chunk.get("choices", [{}])[0]
                                delta = choice.get("delta", {}).get("content", "")
                                if delta:
                                    loop.call_soon_threadsafe(queue.put_nowait, delta)
                            except json.JSONDecodeError:
                                continue
            except Exception as exc:
                error_holder.append(exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _stream)

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token

        if error_holder:
            raise error_holder[0]

    # ── Consensus ────────────────────────────────────────────────────────

    async def consensus_gather(
        self,
        messages: list[dict[str, str]],
        models: list[str],
        *,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        return await self._post(
            "/consensus/gather",
            {
                "messages": messages,
                "models": models,
                "temperature": temperature,
            },
        )

    async def consensus_synthesize(
        self,
        prompt: str,
        models: list[str],
        *,
        arbiter_model: str | None = None,
        tool_name: str = "design",
        temperature: float = 0.7,
        arbiter_temperature: float = 0.3,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": prompt,
            "models": models,
            "tool_name": tool_name,
            "temperature": temperature,
            "arbiter_temperature": arbiter_temperature,
        }
        if arbiter_model:
            body["arbiter_model"] = arbiter_model
        return await self._post("/consensus/synthesize", body)

    # ── Knowledge / Storage ──────────────────────────────────────────────

    async def knowledge_stats(self) -> dict[str, Any]:
        return await self._get("/knowledge/stats")

    async def list_documents(
        self, *, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        return await self._get(
            "/knowledge/documents",
            limit=str(limit),
            offset=str(offset),
        )

    async def store_document(
        self,
        title: str,
        content: str,
        *,
        url: str = "",
        category: str = "",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        return await self._post(
            "/knowledge/documents",
            {
                "title": title,
                "content": content,
                "url": url,
                "category": category,
                "metadata": metadata or {},
            },
        )

    # ── Search ───────────────────────────────────────────────────────────

    async def search_text(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        return await self._get("/search/text", q=query, limit=str(limit))

    async def search_semantic(
        self, vector: list[float], *, limit: int = 10
    ) -> dict[str, Any]:
        return await self._post(
            "/search/semantic",
            {
                "vector": vector,
                "limit": limit,
            },
        )

    async def search_hybrid(
        self,
        query: str,
        vector: list[float],
        *,
        limit: int = 10,
        text_weight: float = 0.5,
    ) -> dict[str, Any]:
        return await self._post(
            "/search/hybrid",
            {
                "query": query,
                "vector": vector,
                "limit": limit,
                "text_weight": text_weight,
            },
        )

    # ── Secrets ──────────────────────────────────────────────────────────

    async def list_secrets(self) -> list[str]:
        resp = await self._get("/secrets/")
        return resp.get("secrets", resp.get("names", []))

    async def get_secret(self, name: str, *, reason: str = "client request") -> str:
        resp = await self._request(
            "POST",
            f"/secrets/{urllib.parse.quote(name)}/reveal",
            extra_headers={"X-Secret-Access-Reason": reason},
        )
        return resp.get("value", "")

    # ── Queue / Pipeline ─────────────────────────────────────────────────

    async def queue_status(self, queue_name: str) -> dict[str, Any]:
        path = f"/pipeline/queues/{urllib.parse.quote(queue_name)}"
        return await self._get(f"{path}/status")

    async def enqueue(self, queue_name: str, payload: dict) -> dict[str, Any]:
        return await self._post(
            f"/pipeline/queues/{urllib.parse.quote(queue_name)}/enqueue",
            {"items": [{"payload": payload}]},
        )

    # ── Graph ────────────────────────────────────────────────────────────

    async def add_node(
        self, label: str, *, node_id: str | None = None, properties: dict | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"label": label}
        if node_id:
            body["id"] = node_id
        if properties:
            body["properties"] = properties
        return await self._post("/graph/nodes", body)

    async def get_node(self, node_id: str) -> dict[str, Any]:
        return await self._get(f"/graph/nodes/{urllib.parse.quote(node_id)}")

    async def get_neighbors(
        self, node_id: str, *, edge_label: str | None = None
    ) -> dict[str, Any]:
        return await self._get(
            f"/graph/nodes/{urllib.parse.quote(node_id)}/neighbors",
            edge_label=edge_label,
        )

    async def add_edge(
        self,
        source: str,
        target: str,
        label: str,
        *,
        edge_id: str | None = None,
        properties: dict | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"source": source, "target": target, "label": label}
        if edge_id:
            body["id"] = edge_id
        if properties:
            body["properties"] = properties
        return await self._post("/graph/edges", body)

    # ── Tools ────────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        resp = await self._get("/tools/")
        return resp.get("tools", [])

    async def call_tool(
        self, name: str, arguments: dict | None = None
    ) -> dict[str, Any]:
        return await self._post(
            "/tools/call",
            {"name": name, "arguments": arguments or {}},
        )

    # ── Resources ────────────────────────────────────────────────────────

    async def list_resources(self) -> list[dict[str, Any]]:
        resp = await self._get("/resources/")
        return resp.get("resources", [])

    async def read_resource(self, uri: str) -> dict[str, Any]:
        return await self._get("/resources/read", uri=uri)
