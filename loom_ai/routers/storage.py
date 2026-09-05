"""Storage domain router for loom-ai REST server."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

from loom_ai.server_models import (
    GetChunksResponse,
    KnowledgeStatsResponse,
    ListDocumentsResponse,
    PendingChunksResponse,
    StoreChunksRequest,
    StoreChunksResponse,
    StoreDocumentRequest,
    StoreDocumentResponse,
    StoreEmbeddingsRequest,
    StoreEmbeddingsResponse,
)


_DOCUMENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _chunk_to_dict(c: Any) -> dict[str, Any]:
    return {
        "id": c.id,
        "document_id": c.document_id,
        "content": c.content,
        "chunk_index": c.chunk_index,
        "sequence": c.chunk_index,
        "content_hash": c.content_hash,
        "token_count": c.token_count,
        "start_offset": c.start_offset,
        "end_offset": c.end_offset,
        "metadata": c.metadata,
        "provenance": c.provenance,
    }


def _extract_chunk_object(c: Any, document_id: str, index: int) -> Any:
    from loom_ai.models import Chunk

    if isinstance(c, str):
        content_hash = hashlib.sha256(c.encode()).hexdigest()[:16]  # noqa: S324
        return Chunk(
            id=f"chunk-{document_id}-{index}",
            document_id=document_id,
            content=c,
            chunk_index=index,
            content_hash=content_hash,
        )

    if isinstance(c, dict):
        chunk_id = c.get("id") or c.get("chunk_id") or f"chunk-{document_id}-{index}"
        doc_id = c.get("document_id") or document_id

        seq = c.get("sequence")
        idx = c.get("chunk_index")
        if seq is not None and idx is not None and int(seq) != int(idx):
            raise ValueError(
                f"Conflicting 'sequence' ({seq}) and 'chunk_index' ({idx}) values provided in chunk payload"
            )
        chosen_seq = seq if seq is not None else (idx if idx is not None else index)
        chunk_idx = int(chosen_seq)

        content = c.get("content") or c.get("text") or ""
        content_hash = (
            c.get("content_hash")
            or hashlib.sha256(str(content).encode()).hexdigest()[:16]
        )  # noqa: S324
        token_count = (
            c.get("token_count")
            if c.get("token_count") is not None
            else c.get("tokens", 0)
        )
        start_offset = c.get("start_offset", 0)
        end_offset = c.get("end_offset", 0)
        metadata = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        provenance = (
            c.get("provenance") if isinstance(c.get("provenance"), dict) else {}
        )

        return Chunk(
            id=str(chunk_id),
            document_id=str(doc_id),
            content=str(content),
            chunk_index=chunk_idx,
            content_hash=str(content_hash),
            token_count=int(token_count),
            start_offset=int(start_offset),
            end_offset=int(end_offset),
            metadata=metadata,
            provenance=provenance,
        )

    if hasattr(c, "content"):
        chunk_id = (
            getattr(c, "id", None)
            or getattr(c, "chunk_id", None)
            or f"chunk-{document_id}-{index}"
        )
        doc_id = getattr(c, "document_id", None) or document_id
        seq = getattr(c, "sequence", None)
        idx = getattr(c, "chunk_index", None)
        if seq is not None and idx is not None and int(seq) != int(idx):
            raise ValueError(
                f"Conflicting 'sequence' ({seq}) and 'chunk_index' ({idx}) values provided in chunk payload"
            )
        chosen_seq = seq if seq is not None else (idx if idx is not None else index)
        chunk_idx = int(chosen_seq)
        content = getattr(c, "content", "")
        content_hash = (
            getattr(c, "content_hash", "")
            or hashlib.sha256(str(content).encode()).hexdigest()[:16]
        )  # noqa: S324
        token_count = getattr(c, "token_count", 0)
        start_offset = getattr(c, "start_offset", 0)
        end_offset = getattr(c, "end_offset", 0)
        metadata = getattr(c, "metadata", {}) or {}
        provenance = getattr(c, "provenance", {}) or {}

        return Chunk(
            id=str(chunk_id),
            document_id=str(doc_id),
            content=str(content),
            chunk_index=chunk_idx,
            content_hash=str(content_hash),
            token_count=int(token_count),
            start_offset=int(start_offset),
            end_offset=int(end_offset),
            metadata=metadata if isinstance(metadata, dict) else {},
            provenance=provenance if isinstance(provenance, dict) else {},
        )

    content_str = str(c)
    return Chunk(
        id=f"chunk-{document_id}-{index}",
        document_id=document_id,
        content=content_str,
        chunk_index=index,
        content_hash=hashlib.sha256(content_str.encode()).hexdigest()[:16],  # noqa: S324
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

    @router.get(
        "/documents/{document_id}",
        responses={
            400: {"description": "Invalid document ID format"},
            404: {"description": "Document not found"},
        },
    )
    async def get_document(document_id: str):
        from fastapi import HTTPException

        if not _DOCUMENT_ID_RE.match(document_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid document ID format",
            )
        doc = await config.storage.get_document(document_id)
        if doc is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )
        return {
            "id": doc.id,
            "stored": True,
            "title": getattr(doc, "title", ""),
            "content": getattr(doc, "content", ""),
            "category": getattr(doc, "category", ""),
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

    @router.get(
        "/documents/{document_id}/chunks",
        response_model=GetChunksResponse,
        responses={
            400: {"description": "Invalid document ID format"},
            404: {"description": "Document not found"},
        },
    )
    async def get_document_chunks(document_id: str):
        from fastapi import HTTPException

        if not _DOCUMENT_ID_RE.match(document_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid document ID format",
            )
        chunks = await config.storage.get_chunks(document_id)
        return {
            "chunks": [_chunk_to_dict(c) for c in chunks],
            "count": len(chunks),
        }

    @router.get("/chunks/pending", response_model=PendingChunksResponse)
    async def pending_chunks(limit: int = 50, after_id: str | None = None):
        chunks = await config.storage.get_pending_chunks(limit, after_id=after_id)
        return {"chunks": [_chunk_to_dict(c) for c in chunks], "count": len(chunks)}

    @router.post("/chunks/store", response_model=StoreChunksResponse)
    async def store_chunks(body: StoreChunksRequest):
        chunks = []
        for i, c in enumerate(body.chunks):
            chunk_obj = _extract_chunk_object(c, body.document_id, i)
            chunks.append(chunk_obj)
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
