"""Tools domain router for loom-ai REST server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    CallToolResponse,
    ListToolsResponse,
    ToolCallRequest,
)


def _mount_tools_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/tools", tags=["tools"], dependencies=auth_deps)

    @router.get("/", response_model=ListToolsResponse)
    async def list_tools():
        tools = await config.tools.list_tools()
        return {"tools": [t.__dict__ for t in tools], "count": len(tools)}

    @router.post("/call", response_model=CallToolResponse)
    async def call_tool(body: ToolCallRequest):
        result = await config.tools.call_tool(body.name, body.arguments)
        return result.__dict__

    app.include_router(router)


