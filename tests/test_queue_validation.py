"""Tests that pipeline/queue POST endpoints return 422 (not 500) on bad input.

Each test sends a request body that is either empty or deliberately omits a
required field and asserts the response is 422 with a descriptive error body.
Valid requests are also tested to confirm they still succeed (200).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from loom_ai.config import LoomConfig
from loom_ai.server import create_app


def _make_client(monkeypatch) -> TestClient:
    """Build a TestClient with all in-memory backends enabled."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.setenv("LOOM_GRAPH", "memory")
    monkeypatch.setenv("LOOM_TOOLS", "memory")
    monkeypatch.setenv("LOOM_RESOURCES", "memory")
    monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
    cfg = LoomConfig.from_env()
    return TestClient(create_app(cfg))


# -- /pipeline/queues/{queue_name}/enqueue ---------------------------------


def test_enqueue_missing_items(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/enqueue", json={})
    assert resp.status_code == 422


def test_enqueue_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/enqueue", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_enqueue_items_wrong_type(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/enqueue", json={"items": "not-a-list"})
    assert resp.status_code == 422


def test_enqueue_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={"items": [{"payload": {"task": "do-something"}}]},
    )
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 1


def test_enqueue_valid_with_id(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={"items": [{"id": "item-1", "payload": {"task": "work"}}]},
    )
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 1


# -- /pipeline/queues/{queue_name}/fetch -----------------------------------


def test_fetch_empty_body_valid(monkeypatch):
    """fetch has all-optional fields, but still requires a JSON object body."""
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/fetch", json={})
    assert resp.status_code == 200


def test_fetch_count_wrong_type(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/fetch", json={"count": "not-int"})
    assert resp.status_code == 422


def test_fetch_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/fetch",
        json={"count": 5, "worker_id": "w-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0  # empty queue


# -- /pipeline/queues/{queue_name}/complete --------------------------------


def test_complete_missing_id(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/complete", json={})
    assert resp.status_code == 422


def test_complete_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/complete", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_complete_id_wrong_type(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/complete", json={"id": ["not", "a", "str"]}
    )
    assert resp.status_code == 422


def test_complete_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/complete", json={"id": "item-1"})
    assert resp.status_code == 200


# -- /pipeline/queues/{queue_name}/requeue ---------------------------------


def test_requeue_missing_items(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/requeue", json={})
    assert resp.status_code == 422


def test_requeue_empty_body(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/requeue", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_requeue_items_wrong_type(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/requeue", json={"items": "bad"})
    assert resp.status_code == 422


def test_requeue_item_missing_id(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/requeue",
        json={"items": [{"payload": {"x": 1}}]},
    )
    assert resp.status_code == 422


def test_requeue_valid(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/requeue",
        json={"items": [{"id": "item-1", "payload": {"task": "retry"}}]},
    )
    assert resp.status_code == 200
    assert resp.json()["requeued"] == 1


# -- Verify 422 detail includes field name --------------------------------


def test_422_detail_mentions_items_field(monkeypatch):
    """The error response should tell the caller *which* field was missing."""
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/enqueue", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    field_names = [err.get("loc", [])[-1] for err in detail if err.get("loc")]
    assert "items" in field_names


def test_422_detail_mentions_id_field(monkeypatch):
    """The error response should tell the caller *which* field was missing."""
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/complete", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    field_names = [err.get("loc", [])[-1] for err in detail if err.get("loc")]
    assert "id" in field_names
