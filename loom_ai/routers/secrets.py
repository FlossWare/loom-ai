"""Secrets domain router for loom-ai REST server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    _NOT_FOUND_RESPONSES,
    GetSecretResponse,
    ListSecretsResponse,
    SecretMetadataResponse,
)


def _mount_secrets_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    """Mount secrets endpoints with hardened access controls.

    Trust boundary
    --------------
    - ``GET /secrets/`` returns secret **names only** (metadata).
    - ``GET /secrets/{name}`` checks existence without returning the value.
    - ``POST /secrets/{name}/reveal`` is the sole path that returns a
      plaintext secret value. It **requires** an ``X-Secret-Access-Reason``
      header so callers must explicitly justify retrieval.  Every reveal
      request is audit-logged regardless of outcome.

    When ``LOOM_API_KEY`` is set, all three endpoints require a valid
    Bearer token.  When unset, localhost binding is the only access
    control -- see the module-level security model note.
    """
    from fastapi import APIRouter, Header, HTTPException

    logger = logging.getLogger("loom_ai.server")
    router = APIRouter(prefix="/secrets", tags=["secrets"], dependencies=auth_deps)

    @router.get("/", response_model=ListSecretsResponse)
    async def list_secrets():
        """Return secret names without exposing values."""
        logger.debug("secrets.list requested")
        names = await config.secrets.list_names()
        return {"secrets": names}

    @router.get(
        "/{name}",
        response_model=SecretMetadataResponse,
        responses=_NOT_FOUND_RESPONSES,
    )
    async def get_secret_metadata(name: str):
        """Check whether a secret exists. Never returns the value."""
        value = await config.secrets.get(name)
        exists = value is not None
        logger.debug("secrets.metadata name=%s exists=%s", name, exists)
        if not exists:
            raise HTTPException(status_code=404, detail="Secret not found")
        return {"name": name, "exists": True}

    @router.post(
        "/{name}/reveal",
        response_model=GetSecretResponse,
        responses=_NOT_FOUND_RESPONSES,
    )
    async def reveal_secret(
        name: str,
        x_secret_access_reason: str | None = Header(None),
    ):
        """Return the plaintext value of a secret.

        Requires ``X-Secret-Access-Reason`` header.  All requests are
        audit-logged with the supplied reason.
        """
        if not x_secret_access_reason:
            logger.warning(  # NOSONAR — intentional audit log
                "secrets.reveal DENIED name=%s reason=missing_header", name
            )
            raise HTTPException(
                status_code=400,
                detail="X-Secret-Access-Reason header is required",
            )
        value = await config.secrets.get(name)
        if value is None:
            logger.info(  # NOSONAR — intentional audit log
                "secrets.reveal NOT_FOUND name=%s reason=%r",
                name,
                x_secret_access_reason,
            )
            raise HTTPException(status_code=404, detail="Secret not found")

        logger.info(  # NOSONAR — intentional audit log
            "secrets.reveal GRANTED name=%s reason=%r",
            name,
            x_secret_access_reason,
        )
        return {"name": name, "value": value}

    app.include_router(router)


