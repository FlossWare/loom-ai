"""Tests that POST endpoints return 422 (not 500) when required fields are missing.

Each test sends a request body that is either empty or deliberately omits a
required field and asserts the response is 422 with a descriptive error body.
"""

from __future__ import annotations

import asyncio

import pytest

# Guard: skip the whole module when fastapi is not installed (e.g. backend
# matrix jobs that only install postgresql/redis/etc extras without server).
pytest.importorskip("fastapi", reason="fastapi not installed (server extra)")

from fastapi.testclient import TestClient  # noqa: E402

from loom_ai.config import LoomConfig  # noqa: E402
from loom_ai.server import create_app  # noqa: E402


def _make_client(monkeypatch) -> TestClient:
    """Build a TestClient with all in-memory backends enabled."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.setenv("LOOM_GRAPH", "memory")
    monkeypatch.setenv("LOOM_TOOLS", "memory")
    monkeypatch.setenv("LOOM_RESOURCES", "memory")
    # LLM + consensus require a base URL; skip — tested separately.
    monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
    cfg = asyncio.run(LoomConfig.from_env())
    return TestClient(create_app(cfg))


# ── /knowledge/documents ──────────────────────────────────────────────


def test_store_document_missing_content(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={"title": "T"})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_store_document_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={})
    assert resp.status_code == 422


def test_store_document_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={"content": "hello"})
    assert resp.status_code == 200
    assert resp.json()["stored"] is True


# ── /knowledge/chunks/store ───────────────────────────────────────────


def test_store_chunks_missing_document_id(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/chunks/store", json={"chunks": ["a"]})
    assert resp.status_code == 422


def test_store_chunks_missing_chunks(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/chunks/store", json={"document_id": "d1"})
    assert resp.status_code == 422


def test_store_chunks_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/chunks/store", json={})
    assert resp.status_code == 422


def test_store_chunks_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/knowledge/chunks/store",
        json={"document_id": "d1", "chunks": ["hello"]},
    )
    assert resp.status_code == 200


# ── /knowledge/chunks/store-embeddings ────────────────────────────────


def test_store_embeddings_missing_embeddings(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/chunks/store-embeddings", json={})
    assert resp.status_code == 422


def test_store_embeddings_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/knowledge/chunks/store-embeddings",
        json={"embeddings": [{"chunk_id": "c1", "vector": [0.1, 0.2]}]},
    )
    assert resp.status_code == 200


# ── /search/semantic ──────────────────────────────────────────────────


def test_semantic_search_missing_vector(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/semantic", json={})
    assert resp.status_code == 422


def test_semantic_search_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/semantic", json={"vector": [0.1, 0.2]})
    assert resp.status_code == 200


# ── /search/hybrid ────────────────────────────────────────────────────


def test_hybrid_search_missing_query(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/hybrid", json={"vector": [0.1]})
    assert resp.status_code == 422


def test_hybrid_search_missing_vector(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/hybrid", json={"query": "hello"})
    assert resp.status_code == 422


def test_hybrid_search_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/hybrid", json={})
    assert resp.status_code == 422


def test_hybrid_search_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/hybrid", json={"query": "hello", "vector": [0.1]})
    assert resp.status_code == 200


# ── /tools/call ───────────────────────────────────────────────────────


def test_tool_call_missing_name(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/tools/call", json={})
    assert resp.status_code == 422


def test_tool_call_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/tools/call", json={"name": "no-such-tool"})
    # The tool may not exist, but the validation should pass (not 422).
    assert resp.status_code != 422


# ── /graph/nodes ──────────────────────────────────────────────────────


def test_add_node_missing_label(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/nodes", json={})
    assert resp.status_code == 422


def test_add_node_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/nodes", json={"label": "Person"})
    assert resp.status_code == 200


# ── /graph/edges ──────────────────────────────────────────────────────


def test_add_edge_missing_source(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/edges", json={"target": "n2", "label": "KNOWS"})
    assert resp.status_code == 422


def test_add_edge_missing_target(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/edges", json={"source": "n1", "label": "KNOWS"})
    assert resp.status_code == 422


def test_add_edge_missing_label(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/edges", json={"source": "n1", "target": "n2"})
    assert resp.status_code == 422


def test_add_edge_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/edges", json={})
    assert resp.status_code == 422


def test_add_edge_valid(monkeypatch):
    client = _make_client(monkeypatch)
    # Edges require existing nodes in the memory backend.
    client.post("/graph/nodes", json={"id": "n1", "label": "Person"})
    client.post("/graph/nodes", json={"id": "n2", "label": "Person"})
    resp = client.post(
        "/graph/edges",
        json={"source": "n1", "target": "n2", "label": "KNOWS"},
    )
    assert resp.status_code == 200


# ── /llm/chat and /consensus/* (need LLM backend) ────────────────────
# These endpoints only exist when LOOM_LLM_BASE_URL is set.  We test
# validation by creating a config with a stub LLM backend.


def _make_llm_client(monkeypatch) -> TestClient:
    """Build a TestClient with a dummy LLM backend so /llm and /consensus
    routes are mounted."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.setenv("LOOM_GRAPH", "memory")
    monkeypatch.setenv("LOOM_TOOLS", "memory")
    monkeypatch.setenv("LOOM_RESOURCES", "memory")
    monkeypatch.setenv("LOOM_LLM_BASE_URL", "http://fake:1234")
    monkeypatch.setenv("LOOM_LLM_API_KEY", "fake-key")
    cfg = asyncio.run(LoomConfig.from_env())
    return TestClient(create_app(cfg))


def test_llm_chat_missing_messages(monkeypatch):
    client = _make_llm_client(monkeypatch)
    resp = client.post("/llm/chat", json={})
    assert resp.status_code == 422


def test_llm_chat_bad_message_item(monkeypatch):
    client = _make_llm_client(monkeypatch)
    # Each message must have role + content.
    resp = client.post("/llm/chat", json={"messages": [{"role": "user"}]})
    assert resp.status_code == 422


def test_consensus_gather_missing_messages(monkeypatch):
    client = _make_llm_client(monkeypatch)
    resp = client.post("/consensus/gather", json={"models": ["gpt-4o"]})
    assert resp.status_code == 422


def test_consensus_gather_missing_models(monkeypatch):
    client = _make_llm_client(monkeypatch)
    resp = client.post(
        "/consensus/gather",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 422


def test_consensus_synthesize_missing_prompt(monkeypatch):
    client = _make_llm_client(monkeypatch)
    resp = client.post("/consensus/synthesize", json={"models": ["gpt-4o"]})
    assert resp.status_code == 422


def test_consensus_synthesize_missing_models(monkeypatch):
    client = _make_llm_client(monkeypatch)
    resp = client.post("/consensus/synthesize", json={"prompt": "hello"})
    assert resp.status_code == 422


def test_consensus_synthesize_empty_body(monkeypatch):
    client = _make_llm_client(monkeypatch)
    resp = client.post("/consensus/synthesize", json={})
    assert resp.status_code == 422


# ── Verify 422 detail includes field name ─────────────────────────────


def test_422_detail_mentions_field(monkeypatch):
    """The error response should tell the caller *which* field was missing."""
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    # FastAPI's default validation error includes the field name.
    field_names = [err.get("loc", [])[-1] for err in detail if err.get("loc")]
    assert "content" in field_names
