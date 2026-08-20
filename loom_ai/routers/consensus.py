"""Consensus domain router for loom-ai REST server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    ConsensusGatherRequest,
    ConsensusSynthesizeRequest,
    GatherResponse,
    SynthesizeResponse,
)


def _mount_consensus_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/consensus", tags=["consensus"], dependencies=auth_deps)

    @router.post("/gather", response_model=GatherResponse)
    async def consensus_gather(body: ConsensusGatherRequest):
        from loom_ai.models import ChatMessage

        messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
        responses, failed = await config.consensus.gather(
            messages, body.models, temperature=body.temperature
        )
        return {
            "responses": [r.__dict__ for r in responses],
            "count": len(responses),
            "failed_models": failed,
            "models_queried": body.models,
        }

    @router.post("/synthesize", response_model=SynthesizeResponse)
    async def consensus_synthesize(body: ConsensusSynthesizeRequest):
        result = await config.consensus.synthesize(
            body.prompt,
            body.models,
            arbiter_model=body.arbiter_model,
            tool_name=body.tool_name,
            temperature=body.temperature,
            arbiter_temperature=body.arbiter_temperature,
        )
        return {
            "synthesis": result.synthesis.__dict__,
            "worker_responses": [r.__dict__ for r in result.worker_responses],
            "failed_models": result.failed_models,
            "arbiter_attempted": result.arbiter_attempted,
            "arbiter_error": result.arbiter_error,
        }

    app.include_router(router)


