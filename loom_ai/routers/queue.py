"""Queue domain router for loom-ai REST server."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    CompleteRequest,
    CompleteResponse,
    EnqueueRequest,
    EnqueueResponse,
    FetchRequest,
    FetchResponse,
    QueueStatusResponse,
    RequeueRequest,
    RequeueResponse,
)


def _mount_queue_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/pipeline", tags=["pipeline"], dependencies=auth_deps)

    @router.get("/queues/{queue_name}/status", response_model=QueueStatusResponse)
    async def queue_status(queue_name: str):
        return await config.queue.status(queue_name)

    @router.post("/queues/{queue_name}/enqueue", response_model=EnqueueResponse)
    async def queue_enqueue(queue_name: str, body: EnqueueRequest):
        from loom_ai.models import QueueItem

        items = [
            QueueItem(
                id=item.id or f"q-{uuid.uuid4().hex[:12]}",
                payload=item.payload,
                enqueued_at=time.time(),
            )
            for i, item in enumerate(body.items)
        ]
        count = await config.queue.enqueue(queue_name, items)
        return {"enqueued": count}

    @router.post("/queues/{queue_name}/fetch", response_model=FetchResponse)
    async def queue_fetch(queue_name: str, body: FetchRequest):
        items = await config.queue.fetch(queue_name, body.count, body.worker_id)
        return {"items": [i.__dict__ for i in items], "count": len(items)}

    @router.post("/queues/{queue_name}/complete", response_model=CompleteResponse)
    async def queue_complete(queue_name: str, body: CompleteRequest):
        ok = await config.queue.complete(queue_name, body.id)
        return {"completed": ok}

    @router.post("/queues/{queue_name}/requeue", response_model=RequeueResponse)
    async def queue_requeue(queue_name: str, body: RequeueRequest):
        from loom_ai.models import QueueItem

        items = [QueueItem(id=item.id, payload=item.payload) for item in body.items]
        count = await config.queue.requeue(queue_name, items)
        return {"requeued": count}

    app.include_router(router)
