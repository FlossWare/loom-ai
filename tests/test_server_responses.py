"""Tests for typed REST response models and error sanitization.

Verifies that every endpoint returns a response matching its declared
Pydantic response model, and that validation errors never echo back
the caller's input values (to prevent secret leakage).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from loom_ai.config import LoomConfig
from loom_ai.server import create_app

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_client(monkeypatch) -> TestClient:
    """Build a TestClient with all in-memory backends enabled."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.setenv("LOOM_GRAPH", "memory")
    monkeypatch.setenv("LOOM_TOOLS", "memory")
    monkeypatch.setenv("LOOM_RESOURCES", "memory")
    monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
    import asyncio

    cfg = asyncio.run(LoomConfig.from_env())
    return TestClient(create_app(cfg))


# ── Response shape tests ─────────────────────────────────────────────────


def test_health_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert isinstance(body["backends"], dict)
    for key in (
        "storage",
        "queue",
        "secrets",
        "embedding",
        "search",
        "graph",
        "llm",
        "consensus",
        "tools",
        "resources",
    ):
        assert key in body["backends"]
        assert isinstance(body["backends"][key], str)


def test_knowledge_stats_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/knowledge/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["documents"], int)
    assert isinstance(body["chunks"], int)
    assert isinstance(body["embeddings"], int)


def test_list_documents_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/knowledge/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["documents"], list)
    assert isinstance(body["limit"], int)
    assert isinstance(body["offset"], int)


def test_store_document_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={"content": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["id"], str)
    assert body["stored"] is True


def test_pending_chunks_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/knowledge/chunks/pending")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["chunks"], list)
    assert isinstance(body["count"], int)


def test_store_chunks_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/knowledge/chunks/store",
        json={"document_id": "d1", "chunks": ["hello"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["stored"], int)
    assert isinstance(body["total"], int)


def test_store_embeddings_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/knowledge/chunks/store-embeddings",
        json={"embeddings": [{"chunk_id": "c1", "vector": [0.1, 0.2]}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["stored"], int)
    assert isinstance(body["total"], int)


def test_text_search_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/search/text?q=hello")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["results"], list)
    assert body["query"] == "hello"


def test_semantic_search_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/search/semantic", json={"vector": [0.1, 0.2]})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["results"], list)


def test_hybrid_search_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/search/hybrid",
        json={"query": "hello", "vector": [0.1]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["results"], list)


def test_list_secrets_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/secrets/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["secrets"], list)


def test_queue_status_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/pipeline/queues/test-q/status")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["pending"], int)
    assert isinstance(body["processing"], int)
    assert isinstance(body["dead_letter"], int)


def test_enqueue_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={"items": [{"payload": {"x": 1}}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["enqueued"], int)


def test_fetch_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/fetch",
        json={"count": 1, "worker_id": "w1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["count"], int)


def test_complete_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    # Enqueue + fetch an item so we can complete it
    client.post(
        "/pipeline/queues/cq/enqueue",
        json={"items": [{"id": "item-1", "payload": {}}]},
    )
    client.post(
        "/pipeline/queues/cq/fetch",
        json={"count": 1, "worker_id": "w1"},
    )
    resp = client.post(
        "/pipeline/queues/cq/complete",
        json={"id": "item-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["completed"], bool)


def test_requeue_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/rq/requeue",
        json={"items": [{"id": "item-1", "payload": {}}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["requeued"], int)


def test_list_tools_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/tools/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["tools"], list)
    assert isinstance(body["count"], int)


def test_list_resources_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/resources/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["resources"], list)
    assert isinstance(body["count"], int)


def test_add_node_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/graph/nodes", json={"label": "Person"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["id"], str)


def test_get_node_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    client.post("/graph/nodes", json={"id": "n1", "label": "Person"})
    resp = client.get("/graph/nodes/n1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "n1"
    assert body["label"] == "Person"
    assert isinstance(body["properties"], dict)


def test_neighbors_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    client.post("/graph/nodes", json={"id": "n1", "label": "Person"})
    resp = client.get("/graph/nodes/n1/neighbors")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["neighbors"], list)


def test_add_edge_response_shape(monkeypatch):
    client = _make_client(monkeypatch)
    client.post("/graph/nodes", json={"id": "n1", "label": "A"})
    client.post("/graph/nodes", json={"id": "n2", "label": "B"})
    resp = client.post(
        "/graph/edges",
        json={"source": "n1", "target": "n2", "label": "KNOWS"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["id"], str)


# ── Validation error sanitization ────────────────────────────────────────


def test_422_does_not_echo_input_values(monkeypatch):
    """Validation errors must never include the caller's submitted input
    values, since those could contain API keys or other secrets."""
    client = _make_client(monkeypatch)
    secret_payload = {"content": 123, "title": "sk-secret-key-12345"}
    resp = client.post("/knowledge/documents", json=secret_payload)
    assert resp.status_code == 422
    body = resp.json()
    # The 'detail' list should NOT contain any 'input' keys
    for err in body["detail"]:
        assert "input" not in err, f"Validation error echoed input value: {err}"


def test_422_still_includes_field_location(monkeypatch):
    """Even after sanitization the error must identify which field failed."""
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={})
    assert resp.status_code == 422
    body = resp.json()
    field_names = [err.get("loc", [])[-1] for err in body["detail"] if err.get("loc")]
    assert "content" in field_names


def test_422_includes_error_type_and_message(monkeypatch):
    """Sanitized errors should still have 'type' and 'msg' for debugging."""
    client = _make_client(monkeypatch)
    resp = client.post("/knowledge/documents", json={})
    assert resp.status_code == 422
    for err in resp.json()["detail"]:
        assert "type" in err
        assert "msg" in err


# ── OpenAPI schema presence ──────────────────────────────────────────────


def test_openapi_schema_has_response_models(monkeypatch):
    """The generated OpenAPI schema should include typed response schemas
    for endpoints that declare a response_model."""
    client = _make_client(monkeypatch)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    paths = schema.get("paths", {})

    # Health endpoint should have a response schema
    health = paths.get("/health", {}).get("get", {})
    health_200 = health.get("responses", {}).get("200", {})
    assert health_200.get("content", {}).get("application/json", {}).get("schema"), (
        "Health endpoint missing response schema"
    )

    # POST /knowledge/documents should have a response schema
    store_doc = paths.get("/knowledge/documents", {}).get("post", {})
    store_200 = store_doc.get("responses", {}).get("200", {})
    assert store_200.get("content", {}).get("application/json", {}).get("schema"), (
        "Store document endpoint missing response schema"
    )

    # Verify schemas reference the named models
    schemas = schema.get("components", {}).get("schemas", {})
    assert "HealthResponse" in schemas
    assert "StoreDocumentResponse" in schemas
    assert "KnowledgeStatsResponse" in schemas
