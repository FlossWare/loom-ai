"""Storage domain router for loom-ai REST server."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    KnowledgeStatsResponse,
    ListDocumentsResponse,
    PendingChunksResponse,
    StoreChunksRequest,
    StoreChunksResponse,
    StoreDocumentRequest,
    StoreDocumentResponse,
    StoreEmbeddingsRequest,
    StoreEmbeddingsResponse,
    _extract_chunk_content,
)


def _mount_storage_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=auth_deps)

    @router.get("/stats", response_model=KnowledgeStatsResponse)
    async def knowledge_stats():
        docs = await config.storage.count_documents()
        chunks = await config.storage.count_chunks()
        embeddings = await config.storage.count_embeddings()
        return {"documents": docs, "chunks": chunks, "embeddings": embeddings}

    @router.get("/documents", response_model=ListDocumentsResponse)
    async def list_documents(limit: int = 20, offset: int = 0):
        docs = await config.storage.list_documents(limit=limit, offset=offset)
        return {
            "documents": [d.__dict__ for d in docs],
            "limit": limit,
            "offset": offset,
        }

    @router.post("/documents", response_model=StoreDocumentResponse)
    async def store_document(body: StoreDocumentRequest):
        from loom_ai.models import Document

        doc = Document(
            id=body.id or f"doc-{uuid.uuid4().hex[:12]}",
            title=body.title,
            content=body.content,
            url=body.url,
            category=body.category,
            metadata=body.metadata,
        )
        doc_id = await config.storage.store_document(doc)
        return {"id": doc_id, "stored": True}

    @router.get("/chunks/pending", response_model=PendingChunksResponse)
    async def pending_chunks(limit: int = 50, after_id: str | None = None):
        chunks = await config.storage.get_pending_chunks(limit, after_id=after_id)
        return {"chunks": [c.__dict__ for c in chunks], "count": len(chunks)}

    @router.post("/chunks/store", response_model=StoreChunksResponse)
    async def store_chunks(body: StoreChunksRequest):
        from loom_ai.models import Chunk

        chunks = []
        for i, c in enumerate(body.chunks):
            content = _extract_chunk_content(c)
            chunks.append(
                Chunk(
                    id=f"chunk-{body.document_id}-{i}",
                    document_id=body.document_id,
                    content=content,
                    chunk_index=i,
                    content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],  # noqa: S324  # NOSONAR — content-addressing hash, not used for security
                )
            )
        stored = await config.storage.store_chunks(body.document_id, chunks)
        return {"stored": stored, "total": len(chunks)}

    @router.post("/chunks/store-embeddings", response_model=StoreEmbeddingsResponse)
    async def store_embeddings(body: StoreEmbeddingsRequest):
        from loom_ai.models import Embedding

        embeddings = []
        for emb in body.embeddings:
            vector = emb.vector or emb.embedding or []
            embeddings.append(
                Embedding(
                    id=f"emb-{emb.chunk_id}",
                    chunk_id=emb.chunk_id,
                    vector=vector,
                    model=emb.model,
                    provider=emb.provider,
                    dimensions=len(vector),
                )
            )
        stored = await config.storage.store_embeddings(embeddings)
        return {"stored": stored, "total": len(embeddings)}

    app.include_router(router)


