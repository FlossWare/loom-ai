"""Public free-gateway demo entrypoint.

Run::

    LOOM_DEMO_PUBLIC=1 python -m loom_ai.server_demo

Mounts the OpenAI-compatible ``/v1`` surface (keyless, brand-neutral) and
restricts the app to health/ready + LLM routes only.  Upstream provider
keys stay server-side via ``LOOM_LLM_*``; callers need nothing Loom-specific.
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("loom_ai.server_demo")

# Routes kept when LOOM_DEMO_PUBLIC=1 (plus anything under /v1 and /llm).
_PUBLIC_PATH_PREFIXES = (
    "/health",
    "/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/v1",
    "/llm",
)


def _strip_non_public_routes(app) -> None:
    """Remove mounts that must not be on the public free surface."""
    kept = []
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        if any(
            path == p or path.startswith(p + "/") or path.startswith(p + "{")
            for p in _PUBLIC_PATH_PREFIXES
        ):
            kept.append(route)
            continue
        if path in ("", "/") and getattr(route, "name", None) in (
            None,
            "swagger_ui_html",
        ):
            kept.append(route)
            continue
        if path.startswith("/docs") or path.startswith("/redoc"):
            kept.append(route)
            continue
        logger.info("demo public: dropping route %s", path)
    app.router.routes = kept


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Install server extra: pip install flossware-loom-ai[server]"
        ) from exc

    # Ensure public mode is on for this entrypoint
    os.environ.setdefault("LOOM_DEMO_PUBLIC", "1")

    from loom_ai.config import LoomConfig
    from loom_ai.public_gateway import demo_public_enabled, mount_public_v1_routes
    from loom_ai.security_bind import require_api_key_for_non_loopback
    from loom_ai.server import create_app

    config = asyncio.run(LoomConfig.from_env())
    app = create_app(config)

    # Brand-neutral OpenAPI metadata
    app.title = "Free LLM Gateway"
    app.description = "OpenAI-compatible free model gateway"
    app.version = "0.1.0"

    if config.llm is not None:
        # Avoid double-mount if create_app already wired /v1 in a future release
        if not any(
            (getattr(r, "path", "") or "").startswith("/v1") for r in app.routes
        ):
            mount_public_v1_routes(app, config)

    if demo_public_enabled():
        _strip_non_public_routes(app)

    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    raw_port = os.environ.get("LOOM_PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f"LOOM_PORT: invalid integer {raw_port!r}") from None
    if not 1 <= port <= 65535:
        raise SystemExit(f"LOOM_PORT: {port} is outside valid range 1-65535")

    require_api_key_for_non_loopback(
        host,
        os.environ.get("LOOM_API_KEY"),
        allow_public_demo=True,
    )

    print(f"Free LLM Gateway → http://{host}:{port}/v1")
    print("  models:  GET  /v1/models")
    print("  chat:    POST /v1/chat/completions")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
