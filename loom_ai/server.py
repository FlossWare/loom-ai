"""Optional FastAPI REST server for loom-ai.

Dynamically mounts routes based on which backends are configured.
Install with: pip install flossware-loom-ai[server]

Security model:
    - Default bind: 127.0.0.1 (localhost only). Override with LOOM_HOST.
    - When LOOM_API_KEY is unset, the server is intentionally unauthenticated.
      This is safe only when bound to localhost or behind a reverse proxy /
      network policy. Do not bind to 0.0.0.0 without setting LOOM_API_KEY.
    - When LOOM_API_KEY is set, all routes except /health and /ready require
      a valid Bearer token.
    - Missing Authorization header: 403 (from HTTPBearer).
      Invalid Bearer token: 401 (from verify_api_key).
    - /secrets/ lists secret names (metadata only, no values).
    - /secrets/{name} returns existence metadata (no value).
    - /secrets/{name}/reveal returns the plaintext value. Callers MUST
      supply an X-Secret-Access-Reason header explaining why the value is
      needed; omitting it returns 400. All reveal requests are audit-logged.
    - When auth is enabled, only callers with the API key can access any
      /secrets endpoint. When auth is disabled, localhost binding is the
      sole access control.

Unauthenticated endpoints:
    /health  -- Liveness probe.  Returns {"status": "healthy"} and backend
                class names.  Always unauthenticated so Kubernetes
                livenessProbe, Docker HEALTHCHECK, and load-balancer health
                checks work without credentials.  Exposes backend *types*
                (e.g. "MemoryStorageBackend") but never connection strings,
                hostnames, or credentials.
    /ready   -- Readiness probe.  Actively pings each required backend and
                returns {"status": "ready"} or {"status": "not_ready"} with
                per-component pass/fail.  Also unauthenticated for probe
                compatibility.  Error messages are sanitized to avoid
                leaking connection details.

Non-loopback exposure:
    When binding to a non-loopback address (e.g. LOOM_HOST=0.0.0.0),
    operators MUST set LOOM_API_KEY.  The unauthenticated /health and
    /ready endpoints are safe to expose because they never include secrets,
    connection strings, or stack traces.

Usage:
    # Auto-configure from LOOM_* env vars:
    python -m loom_ai.server

    # Or programmatically:
    import asyncio
    from loom_ai import LoomConfig
    from loom_ai.server import create_app

    cfg = asyncio.run(LoomConfig.from_env())
    app = create_app(cfg)
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import TYPE_CHECKING

from loom_ai import __version__

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.routers import (
    _mount_consensus_routes,
    _mount_graph_routes,
    _mount_llm_routes,
    _mount_queue_routes,
    _mount_resources_routes,
    _mount_router_routes,
    _mount_search_routes,
    _mount_secrets_routes,
    _mount_storage_routes,
    _mount_tools_routes,
)
from loom_ai.server_models import *  # noqa: F401, F403
from loom_ai.server_models import HealthResponse, ReadinessResponse


def _backend_name(backend: object | None) -> str:
    """Return the class name of *backend*, or ``'disabled'`` when *None*."""
    if backend is None:
        return "disabled"
    return type(backend).__name__


async def _check_backend(name: str, coro) -> dict:
    """Run a single backend health check and return a sanitized result.

    Returns ``{"healthy": True}`` on success, or
    ``{"healthy": False, "error": "<type>"}`` on failure.
    Error messages are limited to the exception type name so that
    connection strings and credentials are never exposed.
    """
    try:
        await coro
        return {"healthy": True}
    except Exception as exc:  # noqa: BLE001
        return {"healthy": False, "error": type(exc).__name__}


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    """Strip ``input`` and ``ctx`` values from validation error details.

    FastAPI echoes back the caller's input in validation errors.  When the
    input contains secret material the echo could leak it in the response.
    The ``ctx`` key may contain raw exception objects that are not JSON
    serialisable and can leak internal implementation details.  This helper
    keeps only ``type``, "loc", "msg", and "url" -- enough for the
    caller to understand what went wrong without revealing submitted values
    or internal state.
    """
    _KEEP = {"type", "loc", "msg", "url"}
    sanitized = []
    for err in errors:
        clean = {k: v for k, v in err.items() if k in _KEEP}
        sanitized.append(clean)
    return sanitized


def create_app(config: LoomConfig) -> FastAPI:
    """Build a FastAPI application wiring only the active backends."""
    try:
        from fastapi import Depends, FastAPI, Security
        from fastapi.exceptions import RequestValidationError
        from starlette.requests import Request
        from starlette.responses import JSONResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI server requires 'fastapi' and 'uvicorn'.  "
            "Install with: pip install flossware-loom-ai[server]"
        ) from exc

    logger = logging.getLogger("loom_ai.server")
    api_key = os.environ.get("LOOM_API_KEY")
    auth_deps: list = []

    if api_key:
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

        security = HTTPBearer()

        async def verify_api_key(
            credentials: HTTPAuthorizationCredentials = Security(security),
        ) -> None:
            if not hmac.compare_digest(credentials.credentials, api_key):
                logger.warning("Invalid API key attempt")
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="Invalid API key")

        auth_deps = [Depends(verify_api_key)]

    app = FastAPI(
        title="loom-ai",
        description="Pluggable AI orchestration API",
        version=__version__,
    )

    app.state.loom = config

    # ── Exception handlers ───────────────────────────────────────────

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return 422 with field-level detail but strip submitted input
        values so that secrets or credentials are never echoed back."""
        return JSONResponse(
            status_code=422,
            content={"detail": _sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled errors.  Returns a generic 500 without
        leaking stack traces or internal implementation details."""
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @app.get("/health", response_model=HealthResponse)
    async def health():
        backends = {
            "storage": type(config.storage).__name__,
            "queue": type(config.queue).__name__,
            "secrets": type(config.secrets).__name__,
            "embedding": type(config.embedding).__name__,
            "search": type(config.search).__name__,
            "graph": _backend_name(config.graph),
            "llm": _backend_name(config.llm),
            "consensus": _backend_name(config.consensus),
            "tools": _backend_name(config.tools),
            "resources": _backend_name(config.resources),
            "router": _backend_name(config.router),
        }
        return {"status": "healthy", "backends": backends}

    @app.get("/ready", response_model=ReadinessResponse)
    async def ready():
        checks: dict = {
            "storage": await _check_backend(
                "storage", config.storage.count_documents()
            ),
            "queue": await _check_backend("queue", config.queue.list_queues()),
            "secrets": await _check_backend("secrets", config.secrets.list_names()),
            "search": await _check_backend(
                "search", config.search.text_search("", limit=1)
            ),
        }
        if config.llm is not None:
            checks["llm"] = await _check_backend("llm", config.llm.list_models())
        if config.graph is not None:
            checks["graph"] = await _check_backend(
                "graph", config.graph.get_entity("__readiness_probe__")
            )
        all_healthy = all(c["healthy"] for c in checks.values())
        status = "ready" if all_healthy else "not_ready"
        return {"status": status, "checks": checks}

    # Mount always-available routers
    _mount_storage_routes(app, config, auth_deps)
    _mount_queue_routes(app, config, auth_deps)
    _mount_search_routes(app, config, auth_deps)
    _mount_secrets_routes(app, config, auth_deps)

    # Mount optional-backend routers
    if config.llm is not None:
        _mount_llm_routes(app, config, auth_deps)

    if config.consensus is not None:
        _mount_consensus_routes(app, config, auth_deps)

    if config.tools is not None:
        _mount_tools_routes(app, config, auth_deps)

    if config.resources is not None:
        _mount_resources_routes(app, config, auth_deps)

    if config.graph is not None:
        _mount_graph_routes(app, config, auth_deps)

    if config.router is not None:
        _mount_router_routes(app, config, auth_deps)

    return app


def main() -> None:
    """Entry point: python -m loom_ai.server"""
    import asyncio

    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "Running the server requires 'uvicorn'.  "
            "Install with: pip install flossware-loom-ai[server]"
        ) from exc

    from loom_ai.config import LoomConfig

    config = asyncio.run(LoomConfig.from_env())
    app = create_app(config)
    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    raw_port = os.environ.get("LOOM_PORT", "5000")
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f"LOOM_PORT: invalid integer {raw_port!r}") from None
    if not 1 <= port <= 65535:
        raise SystemExit(f"LOOM_PORT: {port} is outside valid range 1-65535")
    uvicorn.run(app, host=host, port=port)
