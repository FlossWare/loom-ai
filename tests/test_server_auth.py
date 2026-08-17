"""Tests for server authentication middleware."""

from fastapi.testclient import TestClient


def _make_app(monkeypatch, api_key=None):
    """Create a test app with optional auth."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    if api_key is not None:
        monkeypatch.setenv("LOOM_API_KEY", api_key)
    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    return create_app(LoomConfig.from_env())


def test_health_no_auth_required(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_no_api_key_allows_all(monkeypatch):
    app = _make_app(monkeypatch)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/knowledge/stats").status_code == 200


def test_valid_key_allows_access(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get(
        "/knowledge/stats", headers={"Authorization": "Bearer test-secret"}
    )
    assert resp.status_code == 200


def test_invalid_key_returns_401(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/knowledge/stats", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


def test_missing_auth_header_returns_error(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/knowledge/stats")
    assert resp.status_code in (401, 403)


def test_secrets_requires_auth(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/secrets/")
    assert resp.status_code in (401, 403)


def test_secrets_accessible_with_valid_key(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/secrets/", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200


def test_health_always_unauthenticated(monkeypatch):
    """Health endpoint must be reachable without auth even when API key is set."""
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# /ready endpoint tests
# ---------------------------------------------------------------------------


def test_ready_no_auth_required(monkeypatch):
    """Ready endpoint is unauthenticated even when API key is set."""
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200


def test_ready_returns_status(monkeypatch):
    """Ready endpoint returns status and per-backend checks."""
    app = _make_app(monkeypatch)
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert "checks" in body
    checks = body["checks"]
    assert checks["storage"]["healthy"] is True
    assert checks["queue"]["healthy"] is True
    assert checks["secrets"]["healthy"] is True
    assert checks["search"]["healthy"] is True


def test_ready_with_auth_enabled(monkeypatch):
    """Ready endpoint works without credentials when auth is enabled."""
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/ready")
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "ready"
    assert all(c["healthy"] for c in body["checks"].values())


def test_ready_omits_optional_backends_when_disabled(monkeypatch):
    """Optional backends (llm, graph) are absent from checks when disabled."""
    app = _make_app(monkeypatch)
    client = TestClient(app)
    body = client.get("/ready").json()
    # Default from_env() with no LOOM_LLM_BASE_URL or LOOM_GRAPH disables them
    assert "llm" not in body["checks"]
    assert "graph" not in body["checks"]


def test_ready_includes_optional_backends_when_enabled(monkeypatch):
    """Optional backends appear in checks when configured."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    monkeypatch.setenv("LOOM_GRAPH", "memory")
    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    app = create_app(LoomConfig.from_env())
    client = TestClient(app)
    body = client.get("/ready").json()
    assert "graph" in body["checks"]
    assert body["checks"]["graph"]["healthy"] is True


# ---------------------------------------------------------------------------
# Information disclosure tests
# ---------------------------------------------------------------------------


def test_health_no_sensitive_info(monkeypatch):
    """Health response must not contain connection strings or credentials."""
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/health")
    text = resp.text.lower()
    for sensitive in ("password", "connection", "dsn", "://", "api_key"):
        assert sensitive not in text, f"Health response contains '{sensitive}'"


def test_ready_no_sensitive_info(monkeypatch):
    """Ready response must not contain connection strings or credentials."""
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/ready")
    text = resp.text.lower()
    for sensitive in ("password", "connection", "dsn", "://", "api_key"):
        assert sensitive not in text, f"Ready response contains '{sensitive}'"
