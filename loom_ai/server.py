"""Optional FastAPI REST server for loom-ai.

Dynamically mounts routes based on which backends are configured.
Install with: pip install flossware-loom-ai[server]

Security model:
    - Default bind: 127.0.0.1 (localhost only). Override with LOOM_HOST.
    - When LOOM_API_KEY is unset, the server is intentionally unauthenticated.
      This is safe only when bound to localhost or behind a reverse proxy /
      network policy. Do not bind to 0.0.0.0 without setting LOOM_API_KEY.
    - When LOOM_API_KEY is set, all routes except /health require a valid
      Bearer token. /health is always unauthenticated for probe compatibility.
    - Missing Authorization header: 403 (from HTTPBearer).
      Invalid Bearer token: 401 (from verify_api_key).
    - /secrets/{name} returns plaintext secret values by design. When auth is
      enabled, only callers with the API key can access them. When auth is
      disabled, localhost binding is the sole access control.

Usage:
    # Auto-configure from LOOM_* env vars:
    python -m loom_ai.server

    # Or programmatically:
    from loom_ai import LoomConfig
    from loom_ai.server import create_app

    cfg = LoomConfig.from_env()
    app = create_app(cfg)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import TYPE_CHECKING

from loom_ai import __version__

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

# ---------------------------------------------------------------------------
# Pydantic request models -- FastAPI validates these automatically and returns
# 422 with a descriptive error body when required fields are missing.
#
# Pydantic ships with FastAPI (optional dependency), so the try/except keeps
# the module importable without installing the server extra.
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, Field

    class StoreDocumentRequest(BaseModel):
        content: str
        id: str | None = None
        title: str = "Untitled"
        url: str = ""
        category: str = ""
        metadata: dict = Field(default_factory=dict)

    class StoreChunksRequest(BaseModel):
        document_id: str
        chunks: list

    class EmbeddingItem(BaseModel):
        chunk_id: str = ""
        vector: list[float] | None = None
        embedding: list[float] | None = None
        model: str = "unknown"
        provider: str = "api"

    class StoreEmbeddingsRequest(BaseModel):
        embeddings: list[EmbeddingItem]

    class SemanticSearchRequest(BaseModel):
        vector: list[float]
        limit: int = 10

    class HybridSearchRequest(BaseModel):
        query: str
        vector: list[float]
        limit: int = 10
        text_weight: float = 0.5

    class ChatMessageIn(BaseModel):
        role: str
        content: str

    class LLMChatRequest(BaseModel):
        messages: list[ChatMessageIn]
        model: str | None = None
        temperature: float = 0.7
        max_tokens: int | None = None

    class ConsensusGatherRequest(BaseModel):
        messages: list[ChatMessageIn]
        models: list[str]
        temperature: float = 0.7

    class ConsensusSynthesizeRequest(BaseModel):
        prompt: str
        models: list[str]
        arbiter_model: str | None = None
        tool_name: str = "design"
        temperature: float = 0.7
        arbiter_temperature: float = 0.3

    class ToolCallRequest(BaseModel):
        name: str
        arguments: dict = Field(default_factory=dict)

    class AddNodeRequest(BaseModel):
        label: str
        id: str | None = None
        properties: dict = Field(default_factory=dict)

    class AddEdgeRequest(BaseModel):
        source: str
        target: str
        label: str
        id: str | None = None
        properties: dict = Field(default_factory=dict)

    class QueueItemIn(BaseModel):
        id: str | None = None
        payload: dict = Field(default_factory=dict)

    class EnqueueRequest(BaseModel):
        items: list[QueueItemIn]

    class FetchRequest(BaseModel):
        count: int = 1
        worker_id: str = "unknown"

    class CompleteRequest(BaseModel):
        id: str

    class RequeueItemIn(BaseModel):
        id: str
        payload: dict = Field(default_factory=dict)

    class RequeueRequest(BaseModel):
        items: list[RequeueItemIn]

except ImportError:  # pydantic not installed (server extra not required)
    pass


# ---------------------------------------------------------------------------
# Helper utilities (extracted to reduce cognitive complexity of create_app)
# ---------------------------------------------------------------------------

_NOT_FOUND_RESPONSES: dict = {404: {"description": "Not found"}}


def _backend_name(backend: object | None) -> str:
    """Return the class name of *backend*, or ``'disabled'`` when *None*."""
    if backend is None:
        return "disabled"
    return type(backend).__name__


def _extract_chunk_content(chunk_data: object) -> str:
    """Extract text content from a chunk that may be a string or dict."""
    if isinstance(chunk_data, str):
        return chunk_data
    if isinstance(chunk_data, dict):
        return chunk_data.get("content", "")
    return ""


# ---------------------------------------------------------------------------
# Router-mount helpers -- each creates an APIRouter, registers its endpoints,
# and includes it into *app*.  Keeping them at module level lets create_app()
# stay short and well under the cognitive-complexity threshold.
# ---------------------------------------------------------------------------


def _mount_storage_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=auth_deps)

    @router.get("/stats")
    async def knowledge_stats():
        docs = await config.storage.count_documents()
        chunks = await config.storage.count_chunks()
        embeddings = await config.storage.count_embeddings()
        return {"documents": docs, "chunks": chunks, "embeddings": embeddings}

    @router.get("/documents")
    async def list_documents(limit: int = 20, offset: int = 0):
        docs = await config.storage.list_documents(limit=limit, offset=offset)
        return {
            "documents": [d.__dict__ for d in docs],
            "limit": limit,
            "offset": offset,
        }

    @router.post("/documents")
    async def store_document(body: StoreDocumentRequest):
        from loom_ai.models import Document

        doc = Document(
            id=body.id or f"doc-{int(time.time() * 1000)}",
            title=body.title,
            content=body.content,
            url=body.url,
            category=body.category,
            metadata=body.metadata,
        )
        doc_id = await config.storage.store_document(doc)
        return {"id": doc_id, "stored": True}

    @router.get("/chunks/pending")
    async def pending_chunks(limit: int = 50, after_id: str | None = None):
        chunks = await config.storage.get_pending_chunks(limit, after_id=after_id)
        return {"chunks": [c.__dict__ for c in chunks], "count": len(chunks)}

    @router.post("/chunks/store")
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
                    content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                )
            )
        stored = await config.storage.store_chunks(body.document_id, chunks)
        return {"stored": stored, "total": len(chunks)}

    @router.post("/chunks/store-embeddings")
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


def _mount_queue_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/pipeline", tags=["pipeline"], dependencies=auth_deps)

    @router.get("/queues/{queue_name}/status")
    async def queue_status(queue_name: str):
        return await config.queue.status(queue_name)

    @router.post("/queues/{queue_name}/enqueue")
    async def queue_enqueue(queue_name: str, body: EnqueueRequest):
        from loom_ai.models import QueueItem

        ts = int(time.time() * 1000)
        items = [
            QueueItem(
                id=item.id or f"q-{ts}-{i}",
                payload=item.payload,
                enqueued_at=time.time(),
            )
            for i, item in enumerate(body.items)
        ]
        count = await config.queue.enqueue(queue_name, items)
        return {"enqueued": count}

    @router.post("/queues/{queue_name}/fetch")
    async def queue_fetch(queue_name: str, body: FetchRequest):
        items = await config.queue.fetch(queue_name, body.count, body.worker_id)
        return {"items": [i.__dict__ for i in items], "count": len(items)}

    @router.post("/queues/{queue_name}/complete")
    async def queue_complete(queue_name: str, body: CompleteRequest):
        ok = await config.queue.complete(queue_name, body.id)
        return {"completed": ok}

    @router.post("/queues/{queue_name}/requeue")
    async def queue_requeue(queue_name: str, body: RequeueRequest):
        from loom_ai.models import QueueItem

        items = [QueueItem(id=item.id, payload=item.payload) for item in body.items]
        count = await config.queue.requeue(queue_name, items)
        return {"requeued": count}

    app.include_router(router)


def _mount_search_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/search", tags=["search"], dependencies=auth_deps)

    @router.get("/text")
    async def text_search(q: str, limit: int = 10):
        results = await config.search.text_search(q, limit=limit)
        return {"results": [r.__dict__ for r in results], "query": q}

    @router.post("/semantic")
    async def semantic_search(body: SemanticSearchRequest):
        results = await config.search.semantic_search(body.vector, limit=body.limit)
        return {"results": [r.__dict__ for r in results]}

    @router.post("/hybrid")
    async def hybrid_search(body: HybridSearchRequest):
        results = await config.search.hybrid_search(
            body.query,
            body.vector,
            limit=body.limit,
            text_weight=body.text_weight,
        )
        return {"results": [r.__dict__ for r in results]}

    app.include_router(router)


def _mount_secrets_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/secrets", tags=["secrets"], dependencies=auth_deps)

    @router.get("/")
    async def list_secrets():
        names = await config.secrets.list_names()
        return {"secrets": names}

    @router.get("/{name}", responses=_NOT_FOUND_RESPONSES)
    async def get_secret(name: str):
        value = await config.secrets.get(name)
        if value is None:
            raise HTTPException(status_code=404, detail=f"Secret '{name}' not found")
        return {"name": name, "value": value}

    app.include_router(router)


def _mount_llm_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/llm", tags=["llm"], dependencies=auth_deps)

    @router.get("/models")
    async def llm_models():
        models = await config.llm.list_models()
        return {"models": models, "count": len(models)}

    @router.post("/chat")
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


def _mount_consensus_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/consensus", tags=["consensus"], dependencies=auth_deps)

    @router.post("/gather")
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

    @router.post("/synthesize")
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


def _mount_tools_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter

    router = APIRouter(prefix="/tools", tags=["tools"], dependencies=auth_deps)

    @router.get("/")
    async def list_tools():
        tools = await config.tools.list_tools()
        return {"tools": [t.__dict__ for t in tools], "count": len(tools)}

    @router.post("/call")
    async def call_tool(body: ToolCallRequest):
        result = await config.tools.call_tool(body.name, body.arguments)
        return result.__dict__

    app.include_router(router)


def _mount_resources_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/resources", tags=["resources"], dependencies=auth_deps)

    @router.get("/")
    async def list_resources():
        resources = await config.resources.list_resources()
        return {
            "resources": [r.__dict__ for r in resources],
            "count": len(resources),
        }

    @router.get("/read", responses=_NOT_FOUND_RESPONSES)
    async def read_resource(uri: str):
        try:
            content = await config.resources.read_resource(uri)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Resource not found: {uri!r}")

        if isinstance(content.content, bytes):
            return {
                "uri": content.uri,
                "content": base64.b64encode(content.content).decode("ascii"),
                "mime_type": content.mime_type,
                "encoding": "base64",
            }
        return {
            "uri": content.uri,
            "content": content.content,
            "mime_type": content.mime_type,
            "encoding": "utf-8",
        }

    app.include_router(router)


def _mount_graph_routes(app: FastAPI, config: LoomConfig, auth_deps: list) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/graph", tags=["graph"], dependencies=auth_deps)

    @router.post("/nodes")
    async def add_node(body: AddNodeRequest):
        from loom_ai.models import GraphNode

        node = GraphNode(
            id=body.id or f"node-{int(time.time() * 1000)}",
            label=body.label,
            properties=body.properties,
        )
        node_id = await config.graph.add_node(node)
        return {"id": node_id}

    @router.get("/nodes/{node_id}", responses=_NOT_FOUND_RESPONSES)
    async def get_node(node_id: str):
        node = await config.graph.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return node.__dict__

    @router.get("/nodes/{node_id}/neighbors")
    async def get_neighbors(node_id: str, edge_label: str | None = None):
        neighbors = await config.graph.get_neighbors(node_id, edge_label=edge_label)
        return {"neighbors": [n.__dict__ for n in neighbors]}

    @router.post("/edges")
    async def add_edge(body: AddEdgeRequest):
        from loom_ai.models import GraphEdge

        edge = GraphEdge(
            id=body.id or f"edge-{int(time.time() * 1000)}",
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


def create_app(config: LoomConfig) -> FastAPI:
    """Build a FastAPI application wiring only the active backends."""
    try:
        from fastapi import Depends, FastAPI, Security
    except ImportError as exc:
        raise ImportError(
            "FastAPI server requires 'fastapi' and 'uvicorn'.  "
            "Install with: pip install flossware-loom-ai[server]"
        ) from exc

    logger = logging.getLogger("loom_ai.server")
    api_key = os.environ.get("LOOM_API_KEY")
    auth_deps: list = []

    if api_key:
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

        security = HTTPBearer()

        async def verify_api_key(
            credentials: HTTPAuthorizationCredentials = Security(security),
        ) -> None:
            if not hmac.compare_digest(credentials.credentials, api_key):
                logger.warning("Invalid API key attempt")
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="Invalid API key")

        auth_deps = [Depends(verify_api_key)]

    app = FastAPI(
        title="loom-ai",
        description="Pluggable AI orchestration API",
        version=__version__,
    )

    app.state.loom = config

    @app.get("/health")
    async def health():
        backends = {
            "storage": type(config.storage).__name__,
            "queue": type(config.queue).__name__,
            "secrets": type(config.secrets).__name__,
            "embedding": type(config.embedding).__name__,
            "search": type(config.search).__name__,
            "graph": _backend_name(config.graph),
            "llm": _backend_name(config.llm),
            "consensus": _backend_name(config.consensus),
            "tools": _backend_name(config.tools),
            "resources": _backend_name(config.resources),
        }
        return {"status": "healthy", "backends": backends}

    # Mount always-available routers
    _mount_storage_routes(app, config, auth_deps)
    _mount_queue_routes(app, config, auth_deps)
    _mount_search_routes(app, config, auth_deps)
    _mount_secrets_routes(app, config, auth_deps)

    # Mount optional-backend routers
    if config.llm is not None:
        _mount_llm_routes(app, config, auth_deps)

    if config.consensus is not None:
        _mount_consensus_routes(app, config, auth_deps)

    if config.tools is not None:
        _mount_tools_routes(app, config, auth_deps)

    if config.resources is not None:
        _mount_resources_routes(app, config, auth_deps)

    if config.graph is not None:
        _mount_graph_routes(app, config, auth_deps)

    return app


def main() -> None:
    """Entry point: python -m loom_ai.server"""
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "Running the server requires 'uvicorn'.  "
            "Install with: pip install flossware-loom-ai[server]"
        ) from exc

    from loom_ai.config import LoomConfig

    config = LoomConfig.from_env()
    app = create_app(config)
    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    port = int(os.environ.get("LOOM_PORT", "5000"))
    uvicorn.run(app, host=host, port=port)
