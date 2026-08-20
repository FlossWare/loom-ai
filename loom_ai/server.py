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
    /health  -- Liveness probe.  Returns {\"status\": \"healthy\"} and backend
                class names.  Always unauthenticated so Kubernetes
                livenessProbe, Docker HEALTHCHECK, and load-balancer health
                checks work without credentials.  Exposes backend *types*
                (e.g. \"MemoryStorageBackend\") but never connection strings,
                hostnames, or credentials.
    /ready   -- Readiness probe.  Actively pings each required backend and
                returns {\"status\": \"ready\"} or {\"status\": \"not_ready\"} with
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
\"\"\"

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, Any

from loom_ai import __version__

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

# NOTE: truncated - use full file from artifacts
