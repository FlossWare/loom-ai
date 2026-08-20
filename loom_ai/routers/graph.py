"""Graph domain router for loom-ai REST server."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    _NOT_FOUND_RESPONSES,
    AddEdgeRequest,
    AddNodeRequest,
    IdResponse,
    NeighborsResponse,
    NodeResponse,
)


def _mount_graph_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/graph", tags=["graph"], dependencies=auth_deps)

    @router.post("/nodes", response_model=IdResponse)
    async def add_node(body: AddNodeRequest):
        from loom_ai.models import GraphNode

        node = GraphNode(
            id=body.id or f"node-{uuid.uuid4().hex[:12]}",
            label=body.label,
            properties=body.properties,
        )
        node_id = await config.graph.add_node(node)
        return {"id": node_id}

    @router.get(
        "/nodes/{node_id}",
        response_model=NodeResponse,
        responses=_NOT_FOUND_RESPONSES,
    )
    async def get_node(node_id: str):
        node = await config.graph.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return node.__dict__

    @router.get("/nodes/{node_id}/neighbors", response_model=NeighborsResponse)
    async def get_neighbors(node_id: str, edge_label: str | None = None):
        neighbors = await config.graph.get_neighbors(node_id, edge_label=edge_label)
        return {"neighbors": [n.__dict__ for n in neighbors]}

    @router.post("/edges", response_model=IdResponse)
    async def add_edge(body: AddEdgeRequest):
        from loom_ai.models import GraphEdge

        edge = GraphEdge(
            id=body.id or f"edge-{uuid.uuid4().hex[:12]}",
            source=body.source,
            target=body.target,
            label=body.label,
            properties=body.properties,
        )
        edge_id = await config.graph.add_edge(edge)
        return {"id": edge_id}

    app.include_router(router)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


