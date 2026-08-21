"""Llm domain router for loom-ai REST server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    ChatResponseOut,
    ListModelsResponse,
    LLMChatRequest,
)


def _mount_llm_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/llm", tags=["llm"], dependencies=auth_deps)

    @router.get("/models", response_model=ListModelsResponse)
    async def llm_models():
        models = await config.llm.list_models()
        return {"models": models, "count": len(models)}

    @router.post("/chat", response_model=ChatResponseOut)
    async def llm_chat(body: LLMChatRequest):
        from loom_ai.models import ChatMessage

        messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
        resp = await config.llm.chat(
            messages,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
        return resp.__dict__

    app.include_router(router)
