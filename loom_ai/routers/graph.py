"""Graph domain router for loom-ai REST server."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    _NOT_FOUND_RESPONSES,
    AddEntityRequest,
    AddRelationshipRequest,
    EntityResponse,
    IdResponse,
    RelationshipsResponse,
)


def _mount_graph_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/graph", tags=["graph"], dependencies=auth_deps)

    @router.post("/entities", response_model=IdResponse)
    async def add_entity(body: AddEntityRequest):
        from loom_ai.models_graph import KnowledgeEntity

        entity = KnowledgeEntity(
            id=body.id or f"entity-{uuid.uuid4().hex[:12]}",
            label=body.label,
            entity_type=body.entity_type,
            properties=body.properties,
        )
        entity_id = await config.graph.add_entity(entity)
        return {"id": entity_id}

    @router.get(
        "/entities/{entity_id}",
        response_model=EntityResponse,
        responses=_NOT_FOUND_RESPONSES,
    )
    async def get_entity(entity_id: str):
        entity = await config.graph.get_entity(entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        return entity.__dict__

    @router.get(
        "/entities/{entity_id}/relationships",
        response_model=RelationshipsResponse,
    )
    async def get_relationships(
        entity_id: str,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ):
        rels = await config.graph.get_relationships(
            entity_id,
            relation_type=relation_type,
            direction=direction,
        )
        return {"relationships": [r.__dict__ for r in rels]}

    @router.post("/relationships", response_model=IdResponse)
    async def add_relationship(body: AddRelationshipRequest):
        from loom_ai.models_graph import KnowledgeRelationship

        rel = KnowledgeRelationship(
            id=body.id or f"rel-{uuid.uuid4().hex[:12]}",
            source_id=body.source_id,
            target_id=body.target_id,
            relation_type=body.relation_type,
            properties=body.properties,
        )
        rel_id = await config.graph.add_relationship(rel)
        return {"id": rel_id}

    app.include_router(router)
