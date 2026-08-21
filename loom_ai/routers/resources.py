"""Resources domain router for loom-ai REST server."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    _NOT_FOUND_RESPONSES,
    ListResourcesResponse,
    ReadResourceResponse,
)


def _mount_resources_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/resources", tags=["resources"], dependencies=auth_deps)

    @router.get("/", response_model=ListResourcesResponse)
    async def list_resources():
        resources = await config.resources.list_resources()
        return {
            "resources": [r.__dict__ for r in resources],
            "count": len(resources),
        }

    @router.get(
        "/read",
        response_model=ReadResourceResponse,
        responses=_NOT_FOUND_RESPONSES,
    )
    async def read_resource(uri: str):
        try:
            content = await config.resources.read_resource(uri)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found")

        if isinstance(content.content, bytes):
            return {
                "uri": content.uri,
                "content": base64.b64encode(content.content).decode("ascii"),
                "mime_type": content.mime_type,
                "encoding": "base64",
            }
        return {
            "uri": content.uri,
            "content": content.content,
            "mime_type": content.mime_type,
            "encoding": "utf-8",
        }

    app.include_router(router)
