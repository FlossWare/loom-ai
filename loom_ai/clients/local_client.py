"""In-process client that talks directly to loom-ai backends.

No HTTP, no server process — backends are instantiated from the same
``LOOM_*`` environment variables that ``LoomConfig.from_env()`` reads.

The public API mirrors :class:`~loom_ai.clients.client.LoomClient` so
callers can swap between local and remote mode transparently via
:func:`~loom_ai.clients.get_client`.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from loom_ai.config import LoomConfig

from loom_ai.models import (
    ChatMessage,
    Document,
    GraphEdge,
    GraphNode,
    QueueItem,
)

_NO_GRAPH = "Graph backend not configured"

logger = logging.getLogger(__name__)


def _asdict(obj: object) -> dict[str, Any]:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return dict(obj) if isinstance(obj, dict) else {"value": obj}


class LocalClient:
    """Async client backed by in-process loom-ai backends.

    Usage::

        client = await LocalClient.create()
        response = await client.chat(
            [{"role": "user", "content": "Hello"}]
        )
    """

    def __init__(self, config: LoomConfig) -> None:
        self._cfg = config

    @classmethod
    async def create(cls) -> LocalClient:
        from loom_ai.config import LoomConfig

        config = await LoomConfig.from_env()
        return cls(config)

    @property
    def base_url(self) -> str:
        return "local://"

    # ── Health ───────────────────────────────────────────────────

    async def health(  # NOSONAR — async for API parity
        self,
    ) -> dict[str, Any]:
        return {
            "status": "healthy",
            "mode": "local",
            "backends": {
                "llm": (
                    "configured" if self._cfg.llm else "none"
                ),
                "storage": type(
                    self._cfg.storage
                ).__name__,
                "search": type(
                    self._cfg.search
                ).__name__,
                "graph": (
                    type(self._cfg.graph).__name__
                    if self._cfg.graph
                    else "disabled"
                ),
            },
        }

    async def ready(self) -> dict[str, Any]:
        return await self.health()

    # ── LLM ─────────────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        if not self._cfg.llm:
            return []
        return await self._cfg.llm.list_models()

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not self._cfg.llm:
            raise RuntimeError("No LLM backend configured")
        msgs = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in messages
        ]
        resp = await self._cfg.llm.chat(
            msgs,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _asdict(resp)

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        if not self._cfg.llm:
            raise RuntimeError("No LLM backend configured")
        msgs = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in messages
        ]
        async for token in self._cfg.llm.chat_stream(
            msgs,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield token

    # ── Consensus ────────────────────────────────────────────────

    async def consensus_gather(
        self,
        messages: list[dict[str, str]],
        models: list[str],
        *,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        if not self._cfg.consensus:
            raise RuntimeError("No consensus engine configured")
        msgs = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in messages
        ]
        responses, failed = await self._cfg.consensus.gather(
            msgs, models=models, temperature=temperature,
        )
        return {
            "responses": [_asdict(r) for r in responses],
            "failed_models": failed,
        }

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
        if not self._cfg.consensus:
            raise RuntimeError("No consensus engine configured")
        result = await self._cfg.consensus.synthesize(
            prompt,
            models=models,
            arbiter_model=arbiter_model,
            tool_name=tool_name,
            temperature=temperature,
            arbiter_temperature=arbiter_temperature,
        )
        return _asdict(result)

    # ── Knowledge / Storage ──────────────────────────────────────

    async def knowledge_stats(self) -> dict[str, Any]:
        return {
            "documents": await self._cfg.storage.count_documents(),
            "chunks": await self._cfg.storage.count_chunks(),
            "embeddings": (
                await self._cfg.storage.count_embeddings()
            ),
        }

    async def list_documents(
        self, *, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        docs = await self._cfg.storage.list_documents(
            limit=limit, offset=offset,
        )
        return {"documents": [_asdict(d) for d in docs]}

    async def store_document(
        self,
        title: str,
        content: str,
        *,
        url: str = "",
        category: str = "",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        doc = Document(
            id=uuid.uuid4().hex,
            title=title,
            content=content,
            url=url,
            category=category,
            metadata=metadata or {},
        )
        doc_id = await self._cfg.storage.store_document(doc)
        return {"id": doc_id, "title": title}

    # ── Search ───────────────────────────────────────────────────

    async def search_text(
        self, query: str, *, limit: int = 10
    ) -> dict[str, Any]:
        results = await self._cfg.search.text_search(
            query, limit=limit,
        )
        return {
            "results": [_asdict(r) for r in results],
        }

    async def search_semantic(
        self, vector: list[float], *, limit: int = 10
    ) -> dict[str, Any]:
        results = await self._cfg.search.semantic_search(
            vector, limit=limit,
        )
        return {"results": [_asdict(r) for r in results]}

    async def search_hybrid(
        self,
        query: str,
        vector: list[float],
        *,
        limit: int = 10,
        text_weight: float = 0.5,
    ) -> dict[str, Any]:
        results = await self._cfg.search.hybrid_search(
            query, vector,
            limit=limit, text_weight=text_weight,
        )
        return {"results": [_asdict(r) for r in results]}

    # ── Secrets ──────────────────────────────────────────────────

    async def list_secrets(self) -> list[str]:
        return await self._cfg.secrets.list_names()

    async def get_secret(
        self, name: str, *, reason: str = "client request"
    ) -> str:
        """Return a secret value by *name*.

        ``reason`` is accepted for API parity with :class:`LoomClient` /
        the REST reveal endpoint.  In local mode it is only written to the
        process logger; it is not persisted and is not a remote audit trail.
        """
        logger.info("secrets.get name=%s reason=%r", name, reason)
        value = await self._cfg.secrets.get(name)
        return value or ""

    # ── Queue / Pipeline ─────────────────────────────────────────

    async def queue_status(
        self, queue_name: str
    ) -> dict[str, Any]:
        return await self._cfg.queue.status(queue_name)

    async def enqueue(
        self, queue_name: str, payload: dict
    ) -> dict[str, Any]:
        item = QueueItem(
            id=uuid.uuid4().hex, payload=payload,
        )
        count = await self._cfg.queue.enqueue(
            queue_name, [item],
        )
        return {"enqueued": count, "item_id": item.id}

    # ── Graph ────────────────────────────────────────────────────

    async def add_node(
        self,
        label: str,
        *,
        node_id: str | None = None,
        properties: dict | None = None,
    ) -> dict[str, Any]:
        if not self._cfg.graph:
            raise RuntimeError(_NO_GRAPH)
        node = GraphNode(
            id=node_id or uuid.uuid4().hex,
            label=label,
            properties=properties or {},
        )
        nid = await self._cfg.graph.add_node(node)
        return {"id": nid, "label": label}

    async def get_node(
        self, node_id: str
    ) -> dict[str, Any]:
        if not self._cfg.graph:
            raise RuntimeError(_NO_GRAPH)
        node = await self._cfg.graph.get_node(node_id)
        if node is None:
            return {"error": "not found"}
        return _asdict(node)

    async def get_neighbors(
        self,
        node_id: str,
        *,
        edge_label: str | None = None,
    ) -> dict[str, Any]:
        if not self._cfg.graph:
            raise RuntimeError(_NO_GRAPH)
        nodes = await self._cfg.graph.get_neighbors(
            node_id, edge_label=edge_label,
        )
        return {"neighbors": [_asdict(n) for n in nodes]}

    async def add_edge(
        self,
        source: str,
        target: str,
        label: str,
        *,
        edge_id: str | None = None,
        properties: dict | None = None,
    ) -> dict[str, Any]:
        if not self._cfg.graph:
            raise RuntimeError(_NO_GRAPH)
        edge = GraphEdge(
            id=edge_id or uuid.uuid4().hex,
            source=source,
            target=target,
            label=label,
            properties=properties or {},
        )
        eid = await self._cfg.graph.add_edge(edge)
        return {"id": eid, "label": label}

    # ── Tools ────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        if not self._cfg.tools:
            return []
        tools = await self._cfg.tools.list_tools()
        return [_asdict(t) for t in tools]

    async def call_tool(
        self, name: str, arguments: dict | None = None
    ) -> dict[str, Any]:
        if not self._cfg.tools:
            raise RuntimeError("Tools not configured")
        result = await self._cfg.tools.call_tool(
            name, arguments or {},
        )
        return _asdict(result)

    # ── Resources ────────────────────────────────────────────────

    async def list_resources(self) -> list[dict[str, Any]]:
        if not self._cfg.resources:
            return []
        resources = await self._cfg.resources.list_resources()
        return [_asdict(r) for r in resources]

    async def read_resource(
        self, uri: str
    ) -> dict[str, Any]:
        if not self._cfg.resources:
            raise RuntimeError("Resources not configured")
        content = await self._cfg.resources.read_resource(uri)
        return _asdict(content)
