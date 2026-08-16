"""Protocol conformance tests for REST API contracts.

Verifies that concrete stub implementations satisfy each protocol via
``isinstance`` checks (enabled by ``@runtime_checkable``), and that
the data models can be constructed with expected defaults.
"""

from __future__ import annotations

from loom_ai.contracts_api import (
    ErrorHandler,
    Middleware,
    RequestLifecycle,
)
from loom_ai.models_api import (
    APIError,
    APIRequest,
    APIResponse,
    AuthContext,
    MiddlewareContext,
)

# -- Stub implementations -------------------------------------------------


class StubRequestLifecycle:
    """Minimal stub satisfying the RequestLifecycle protocol."""

    async def validate(self, request):
        pass

    async def authorize(self, request):
        return AuthContext(authenticated=True, principal="stub-user")

    async def execute(self, request, auth):
        return {"ok": True}

    async def respond(self, result, *, request_id=""):
        return APIResponse(status_code=200, body=result, request_id=request_id)


class StubErrorHandler:
    """Minimal stub satisfying the ErrorHandler protocol."""

    async def handle(self, error, *, request_id=""):
        return APIError(
            code="INTERNAL",
            message=str(error),
            status_code=500,
            request_id=request_id,
        )

    async def format_error(self, api_error):
        return APIResponse(
            status_code=api_error.status_code,
            body={"code": api_error.code, "message": api_error.message},
            request_id=api_error.request_id,
        )


class StubMiddleware:
    """Minimal stub satisfying the Middleware protocol."""

    async def before_request(self, context):
        return context

    async def after_request(self, context):
        return context


# -- Protocol conformance tests --------------------------------------------


def test_request_lifecycle_conformance():
    """StubRequestLifecycle satisfies the RequestLifecycle protocol."""
    assert isinstance(StubRequestLifecycle(), RequestLifecycle)


def test_error_handler_conformance():
    """StubErrorHandler satisfies the ErrorHandler protocol."""
    assert isinstance(StubErrorHandler(), ErrorHandler)


def test_middleware_conformance():
    """StubMiddleware satisfies the Middleware protocol."""
    assert isinstance(StubMiddleware(), Middleware)


# -- Dataclass construction tests ------------------------------------------


def test_api_request_defaults():
    """APIRequest has expected default values."""
    req = APIRequest(method="GET", path="/api/v1/tasks")
    assert req.method == "GET"
    assert req.path == "/api/v1/tasks"
    assert req.headers == {}
    assert req.query_params == {}
    assert req.body is None
    assert req.client_ip == ""
    assert req.request_id == ""


def test_api_request_full():
    """APIRequest accepts all fields."""
    req = APIRequest(
        method="POST",
        path="/api/v1/tasks",
        headers={"Content-Type": "application/json"},
        query_params={"verbose": "true"},
        body={"task": "classify this"},
        client_ip="127.0.0.1",
        request_id="req-42",
    )
    assert req.body == {"task": "classify this"}
    assert req.headers["Content-Type"] == "application/json"
    assert req.request_id == "req-42"


def test_api_response_defaults():
    """APIResponse has expected default values."""
    resp = APIResponse(status_code=200)
    assert resp.status_code == 200
    assert resp.body is None
    assert resp.headers == {}
    assert resp.request_id == ""


def test_api_response_with_body():
    """APIResponse carries a JSON body."""
    resp = APIResponse(
        status_code=201,
        body={"id": "t-1"},
        request_id="req-1",
    )
    assert resp.status_code == 201
    assert resp.body == {"id": "t-1"}


def test_auth_context_defaults():
    """AuthContext starts unauthenticated."""
    auth = AuthContext()
    assert auth.authenticated is False
    assert auth.principal == ""
    assert auth.roles == []
    assert auth.scopes == []
    assert auth.metadata == {}


def test_auth_context_populated():
    """AuthContext can be fully populated."""
    auth = AuthContext(
        authenticated=True,
        principal="user@example.com",
        roles=["admin"],
        scopes=["read", "write"],
        metadata={"tenant": "acme"},
    )
    assert auth.authenticated is True
    assert "admin" in auth.roles
    assert auth.metadata["tenant"] == "acme"


def test_api_error_defaults():
    """APIError has expected default values."""
    err = APIError(code="NOT_FOUND", message="Resource not found")
    assert err.code == "NOT_FOUND"
    assert err.message == "Resource not found"
    assert err.status_code == 500
    assert err.details == {}
    assert err.request_id == ""


def test_api_error_with_details():
    """APIError carries extra details."""
    err = APIError(
        code="VALIDATION",
        message="Invalid body",
        status_code=422,
        details={"field": "name", "reason": "required"},
        request_id="req-99",
    )
    assert err.status_code == 422
    assert err.details["field"] == "name"


def test_middleware_context_defaults():
    """MiddlewareContext starts with all-None/empty defaults."""
    ctx = MiddlewareContext()
    assert ctx.request is None
    assert ctx.response is None
    assert ctx.auth is None
    assert ctx.metadata == {}
    assert ctx.aborted is False


def test_middleware_context_populated():
    """MiddlewareContext can carry request, response and auth."""
    req = APIRequest(method="GET", path="/health")
    resp = APIResponse(status_code=200)
    auth = AuthContext(authenticated=True, principal="svc")
    ctx = MiddlewareContext(request=req, response=resp, auth=auth)
    assert ctx.request is req
    assert ctx.response is resp
    assert ctx.auth is auth
    assert ctx.aborted is False


# -- Async stub behaviour tests -------------------------------------------


async def test_lifecycle_validate_succeeds():
    """RequestLifecycle.validate returns None on valid input."""
    lc = StubRequestLifecycle()
    req = APIRequest(method="GET", path="/")
    result = await lc.validate(req)
    assert result is None


async def test_lifecycle_authorize_returns_auth():
    """RequestLifecycle.authorize returns an AuthContext."""
    lc = StubRequestLifecycle()
    req = APIRequest(method="GET", path="/")
    auth = await lc.authorize(req)
    assert isinstance(auth, AuthContext)
    assert auth.authenticated is True


async def test_lifecycle_execute_returns_result():
    """RequestLifecycle.execute returns business result."""
    lc = StubRequestLifecycle()
    req = APIRequest(method="POST", path="/run")
    auth = AuthContext(authenticated=True)
    result = await lc.execute(req, auth)
    assert result == {"ok": True}


async def test_lifecycle_respond_builds_response():
    """RequestLifecycle.respond wraps result in APIResponse."""
    lc = StubRequestLifecycle()
    resp = await lc.respond({"data": 1}, request_id="r-1")
    assert isinstance(resp, APIResponse)
    assert resp.status_code == 200
    assert resp.request_id == "r-1"


async def test_error_handler_handle():
    """ErrorHandler.handle converts an exception to APIError."""
    eh = StubErrorHandler()
    err = await eh.handle(ValueError("bad input"), request_id="r-2")
    assert isinstance(err, APIError)
    assert err.code == "INTERNAL"
    assert "bad input" in err.message


async def test_error_handler_format_error():
    """ErrorHandler.format_error renders an APIError as APIResponse."""
    eh = StubErrorHandler()
    api_err = APIError(code="NOT_FOUND", message="gone", status_code=404)
    resp = await eh.format_error(api_err)
    assert isinstance(resp, APIResponse)
    assert resp.status_code == 404
    assert resp.body["code"] == "NOT_FOUND"


async def test_middleware_before_request():
    """Middleware.before_request passes context through."""
    mw = StubMiddleware()
    ctx = MiddlewareContext(
        request=APIRequest(method="GET", path="/"),
        metadata={"trace": "abc"},
    )
    result = await mw.before_request(ctx)
    assert result is ctx
    assert result.metadata["trace"] == "abc"


async def test_middleware_after_request():
    """Middleware.after_request passes context through."""
    mw = StubMiddleware()
    ctx = MiddlewareContext(
        response=APIResponse(status_code=200),
    )
    result = await mw.after_request(ctx)
    assert result is ctx
