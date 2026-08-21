"""Router_routes domain router for loom-ai REST server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    RouterHealthResponse,
    RouterModelsResponse,
    RouterOutcomeRequest,
    RouterOutcomeResponse,
    RouterPerformanceResponse,
    RouterProfileRequest,
    RouterProfileResponse,
    RouterRegisterRequest,
    RouterRegisterResponse,
    RouterSelectRequest,
    RouterSelectResponse,
)


def _mount_router_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router_api = APIRouter(
        prefix="/router",
        tags=["router"],
        dependencies=auth_deps,
    )

    @router_api.post(
        "/select",
        response_model=RouterSelectResponse,
        responses={400: {"description": "Invalid task type or candidates"}},
    )
    async def router_select(body: RouterSelectRequest):
        try:
            model = await config.router.select(
                body.task_type,
                candidates=body.candidates,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"model": model, "task_type": body.task_type}

    @router_api.post("/outcome", response_model=RouterOutcomeResponse)
    async def router_outcome(body: RouterOutcomeRequest):
        await config.router.record_outcome(
            body.model,
            body.task_type,
            reward=body.reward,
        )
        return {"recorded": True}

    @router_api.get(
        "/performance",
        response_model=RouterPerformanceResponse,
    )
    async def router_performance(task_type: str | None = None):
        arms = await config.router.performance(task_type=task_type)
        return {"arms": arms}

    @router_api.get("/models", response_model=RouterModelsResponse)
    async def router_models():
        models = await config.router.list_available_models()
        return {
            "models": [m.__dict__ for m in models],
            "count": len(models),
        }

    @router_api.get("/health", response_model=RouterHealthResponse)
    async def router_health():
        health = await config.router.provider_health()
        return {"providers": {k: v.__dict__ for k, v in health.items()}}

    @router_api.post("/register", response_model=RouterRegisterResponse)
    async def router_register(body: RouterRegisterRequest):
        await config.router.register_provider(
            body.provider_name,
            None,
            models=body.models,
            priority=body.priority,
        )
        return {
            "provider_name": body.provider_name,
            "models_registered": len(body.models),
        }

    @router_api.post("/profile", response_model=RouterProfileResponse)
    async def router_profile(body: RouterProfileRequest):
        from loom_ai.backends.adaptive_router import ModelCapabilityProfile

        config.router.set_profile(
            body.model,
            ModelCapabilityProfile(
                model=body.model,
                capabilities=body.capabilities,
                strengths=body.strengths,
            ),
        )
        return {"model": body.model, "capabilities": body.capabilities}

    app.include_router(router_api)
