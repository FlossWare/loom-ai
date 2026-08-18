"""Tests that pipeline/queue POST endpoints return 422 (not 500) on bad input.

Each test sends a request body that is either empty or deliberately omits a
required field and asserts the response is 422 with a descriptive error body.
Valid requests are also tested to confirm they still succeed (200).
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
    monkeypatch.delenv("LOOM_LLM_BASE_URL", raising=False)
    cfg = asyncio.run(LoomConfig.from_env())
    return TestClient(create_app(cfg))


# -- /pipeline/queues/{queue_name}/enqueue ---------------------------------


def test_enqueue_missing_items(monkeypatch):
    """Empty body (no items, no payload) should return 422."""
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/enqueue", json={})
    assert resp.status_code == 422


def test_enqueue_empty_body(monkeypatch):
    """Empty body should return 422 with detail."""
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


# -- Single-item shorthand (issue #230) ------------------------------------


def test_enqueue_single_item_shorthand(monkeypatch):
    """Single item body without 'items' wrapper should be accepted."""
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={"payload": {"task": "x"}},
    )
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 1


def test_enqueue_single_item_with_id(monkeypatch):
    """Single item with explicit id should be accepted."""
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={"id": "custom-id", "payload": {"task": "y"}},
    )
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 1


def test_enqueue_wrapped_form_still_works(monkeypatch):
    """The original wrapped form must continue to work."""
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={"items": [{"payload": {"a": 1}}, {"payload": {"b": 2}}]},
    )
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 2


def test_enqueue_no_items_no_payload_returns_422(monkeypatch):
    """Body with neither 'items' nor 'payload' should be rejected."""
    client = _make_client(monkeypatch)
    resp = client.post(
        "/pipeline/queues/test-q/enqueue",
        json={},
    )
    assert resp.status_code == 422


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


def test_422_detail_mentions_items_or_payload(monkeypatch):
    """The error response should tell the caller what was expected."""
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/enqueue", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    # The model_validator raises a descriptive error mentioning 'items' and 'payload'
    detail_text = str(detail)
    assert "items" in detail_text or "payload" in detail_text


def test_422_detail_mentions_id_field(monkeypatch):
    """The error response should tell the caller *which* field was missing."""
    client = _make_client(monkeypatch)
    resp = client.post("/pipeline/queues/test-q/complete", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    field_names = [err.get("loc", [])[-1] for err in detail if err.get("loc")]
    assert "id" in field_names
