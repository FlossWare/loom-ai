"""Search domain router for loom-ai REST server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    HybridSearchRequest,
    HybridSearchResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    TextSearchResponse,
)


def _mount_search_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/search", tags=["search"], dependencies=auth_deps)

    @router.get("/text", response_model=TextSearchResponse)
    async def text_search(q: str, limit: int = 10):
        results = await config.search.text_search(q, limit=limit)
        return {"results": [r.__dict__ for r in results], "query": q}

    @router.post("/semantic", response_model=SemanticSearchResponse)
    async def semantic_search(body: SemanticSearchRequest):
        results = await config.search.semantic_search(body.vector, limit=body.limit)
        return {"results": [r.__dict__ for r in results]}

    @router.post("/hybrid", response_model=HybridSearchResponse)
    async def hybrid_search(body: HybridSearchRequest):
        results = await config.search.hybrid_search(
            body.query,
            body.vector,
            limit=body.limit,
            text_weight=body.text_weight,
        )
        return {"results": [r.__dict__ for r in results]}

    app.include_router(router)


