"""Tests for LocalClient and get_client() factory."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from loom_ai.clients import get_client
from loom_ai.clients.client import LoomClient
from loom_ai.clients.local_client import LocalClient, _asdict


def _clean_env() -> dict[str, str]:
    """Return env dict with remote-mode vars stripped."""
    return {k: v for k, v in os.environ.items() if k not in ("LOOM_URL", "LOOM_HOST")}


def _clean_env_no_llm() -> dict[str, str]:
    """Return env dict with remote and LLM vars stripped."""
    return {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "LOOM_URL",
            "LOOM_HOST",
            "LOOM_LLM_BASE_URL",
            "LOOM_LLM_API_KEY",
        )
    }


async def _make_local_client() -> LocalClient:
    with patch.dict(os.environ, _clean_env(), clear=True):
        return await LocalClient.create()


# ── _asdict helper ──────────────────────────────────────────────


class TestAsDict:
    def test_dataclass(self):
        from loom_ai.models import ChatMessage

        msg = ChatMessage(role="user", content="hi")
        result = _asdict(msg)
        assert result == {"role": "user", "content": "hi"}

    def test_dict_passthrough(self):
        d = {"a": 1, "b": 2}
        assert _asdict(d) == {"a": 1, "b": 2}

    def test_other_type(self):
        assert _asdict(42) == {"value": 42}

    def test_nested_dataclass(self):
        from loom_ai.models import Document

        doc = Document(
            id="abc",
            title="Test",
            content="Body",
            metadata={"tag": "v1"},
        )
        result = _asdict(doc)
        assert result["id"] == "abc"
        assert result["metadata"] == {"tag": "v1"}


# ── get_client() factory ────────────────────────────────────────


class TestGetClient:
    @pytest.mark.asyncio
    async def test_returns_loom_client_when_url_set(self):
        with patch.dict(os.environ, {"LOOM_URL": "http://example:5000"}):
            client = await get_client()
        assert isinstance(client, LoomClient)

    @pytest.mark.asyncio
    async def test_host_alone_does_not_trigger_remote(self):
        with patch.dict(os.environ, {"LOOM_HOST": "myhost"}, clear=False):
            client = await get_client()
        assert isinstance(client, LocalClient)

    @pytest.mark.asyncio
    async def test_returns_local_client_when_no_remote(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            client = await get_client()
        assert isinstance(client, LocalClient)


# ── LocalClient basics ──────────────────────────────────────────


class TestLocalClientHealth:
    @pytest.mark.asyncio
    async def test_health_returns_mode_local(self):
        client = await _make_local_client()
        resp = await client.health()
        assert resp["mode"] == "local"
        assert resp["status"] == "healthy"
        assert "backends" in resp

    @pytest.mark.asyncio
    async def test_ready_delegates_to_health(self):
        client = await _make_local_client()
        ready = await client.ready()
        health = await client.health()
        assert ready == health

    @pytest.mark.asyncio
    async def test_base_url_is_local(self):
        client = await _make_local_client()
        assert client.base_url == "local://"


# ── LLM ─────────────────────────────────────────────────────────


class TestLocalClientLLM:
    @pytest.mark.asyncio
    async def test_list_models_returns_list(self):
        client = await _make_local_client()
        models = await client.list_models()
        assert isinstance(models, list)

    @pytest.mark.asyncio
    async def test_chat_raises_without_llm(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        with pytest.raises(RuntimeError, match="No LLM"):
            await client.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_stream_raises_without_llm(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        with pytest.raises(RuntimeError, match="No LLM"):
            async for _ in client.chat_stream([{"role": "user", "content": "hi"}]):
                pass


# ── Consensus ────────────────────────────────────────────────────


class TestLocalClientConsensus:
    @pytest.mark.asyncio
    async def test_gather_raises_without_consensus(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        with pytest.raises(RuntimeError, match="No consensus"):
            await client.consensus_gather(
                [{"role": "user", "content": "hi"}],
                models=["m1"],
            )

    @pytest.mark.asyncio
    async def test_synthesize_raises_without_consensus(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        with pytest.raises(RuntimeError, match="No consensus"):
            await client.consensus_synthesize(
                "prompt",
                models=["m1"],
            )


# ── Knowledge / Storage ─────────────────────────────────────────


class TestLocalClientStorage:
    @pytest.mark.asyncio
    async def test_knowledge_stats(self):
        client = await _make_local_client()
        stats = await client.knowledge_stats()
        assert "documents" in stats
        assert "chunks" in stats
        assert "embeddings" in stats

    @pytest.mark.asyncio
    async def test_store_and_list_documents(self):
        client = await _make_local_client()
        resp = await client.store_document(
            "Test Doc",
            "Test content",
            category="testing",
        )
        assert "id" in resp
        assert resp["title"] == "Test Doc"

        docs_resp = await client.list_documents()
        assert "documents" in docs_resp
        titles = [d["title"] for d in docs_resp["documents"]]
        assert "Test Doc" in titles


# ── Search ───────────────────────────────────────────────────────


class TestLocalClientSearch:
    @pytest.mark.asyncio
    async def test_search_text(self):
        client = await _make_local_client()
        resp = await client.search_text("test query")
        assert "results" in resp
        assert isinstance(resp["results"], list)

    @pytest.mark.asyncio
    async def test_search_semantic(self):
        client = await _make_local_client()
        resp = await client.search_semantic([0.1, 0.2, 0.3])
        assert "results" in resp

    @pytest.mark.asyncio
    async def test_search_hybrid(self):
        client = await _make_local_client()
        resp = await client.search_hybrid(
            "test",
            [0.1, 0.2],
            text_weight=0.6,
        )
        assert "results" in resp


# ── Secrets ──────────────────────────────────────────────────────


class TestLocalClientSecrets:
    @pytest.mark.asyncio
    async def test_list_secrets(self):
        client = await _make_local_client()
        names = await client.list_secrets()
        assert isinstance(names, list)

    @pytest.mark.asyncio
    async def test_get_secret_missing(self):
        client = await _make_local_client()
        value = await client.get_secret("nonexistent")
        assert isinstance(value, str)


# ── Queue ────────────────────────────────────────────────────────


class TestLocalClientQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_status(self):
        client = await _make_local_client()
        resp = await client.enqueue(
            "test-queue",
            {"task": "process"},
        )
        assert "enqueued" in resp
        assert "item_id" in resp

        status = await client.queue_status("test-queue")
        assert isinstance(status, dict)


# ── Graph ────────────────────────────────────────────────────────


class TestLocalClientGraph:
    @pytest.mark.asyncio
    async def test_graph_raises_when_disabled(self):
        client = await _make_local_client()
        if not client._cfg.graph:
            with pytest.raises(RuntimeError, match="Graph backend"):
                await client.add_node("test")
            with pytest.raises(RuntimeError, match="Graph backend"):
                await client.get_node("x")
            with pytest.raises(RuntimeError, match="Graph backend"):
                await client.get_neighbors("x")
            with pytest.raises(RuntimeError, match="Graph backend"):
                await client.add_edge("a", "b", "rel")

    @pytest.mark.asyncio
    async def test_graph_operations_with_memory_backend(self):
        env = {**_clean_env(), "LOOM_GRAPH": "memory"}
        with patch.dict(os.environ, env, clear=True):
            client = await LocalClient.create()

        node_resp = await client.add_node(
            "person",
            node_id="n1",
            properties={"name": "Alice"},
        )
        assert node_resp["id"] == "n1"
        assert node_resp["label"] == "person"

        get_resp = await client.get_node("n1")
        assert get_resp["label"] == "person"

        await client.add_node("person", node_id="n2")
        edge_resp = await client.add_edge(
            "n1",
            "n2",
            "knows",
            edge_id="e1",
        )
        assert edge_resp["id"] == "e1"

        neighbors = await client.get_neighbors("n1")
        assert "neighbors" in neighbors

    @pytest.mark.asyncio
    async def test_get_node_not_found(self):
        env = {**_clean_env(), "LOOM_GRAPH": "memory"}
        with patch.dict(os.environ, env, clear=True):
            client = await LocalClient.create()

        resp = await client.get_node("nonexistent")
        assert resp.get("error") == "not found"


# ── Tools ────────────────────────────────────────────────────────


class TestLocalClientTools:
    @pytest.mark.asyncio
    async def test_list_tools_empty_when_disabled(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        tools = await client.list_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_raises_when_disabled(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        with pytest.raises(RuntimeError, match="Tools"):
            await client.call_tool("some_tool")


# ── Resources ────────────────────────────────────────────────────


class TestLocalClientResources:
    @pytest.mark.asyncio
    async def test_list_resources_empty_when_disabled(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        resources = await client.list_resources()
        assert resources == []

    @pytest.mark.asyncio
    async def test_read_resource_raises_when_disabled(self):
        with patch.dict(os.environ, _clean_env_no_llm(), clear=True):
            client = await LocalClient.create()
        with pytest.raises(RuntimeError, match="Resources"):
            await client.read_resource("file:///test")
