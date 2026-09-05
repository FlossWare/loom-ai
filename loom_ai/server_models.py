"""Pydantic request/response models for the loom-ai REST server.

Extracted from server.py to allow router modules to import models
without circular dependencies.
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, Field, model_validator

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

    class AddEntityRequest(BaseModel):
        label: str
        entity_type: str
        id: str | None = None
        properties: dict = Field(default_factory=dict)

    class AddRelationshipRequest(BaseModel):
        source_id: str
        target_id: str
        relation_type: str
        id: str | None = None
        properties: dict = Field(default_factory=dict)

    class QueueItemIn(BaseModel):
        id: str | None = None
        payload: dict = Field(default_factory=dict)

    class EnqueueRequest(BaseModel):
        items: list[QueueItemIn] = []

        @model_validator(mode="before")
        @classmethod
        def _accept_single_item(cls, data):
            if isinstance(data, dict) and "items" not in data:
                if "payload" in data:
                    return {"items": [data]}
                raise ValueError(
                    "Request must contain 'items' list or a single-item 'payload'"
                )
            return data

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

    # ------------------------------------------------------------------
    # Pydantic response models -- used as ``response_model`` on each
    # FastAPI endpoint so the OpenAPI schema accurately describes every
    # response and FastAPI strips any unexpected fields before returning.
    # ------------------------------------------------------------------

    # ── Sub-models for nested response data ──────────────────────────

    class BackendCheckResult(BaseModel):
        healthy: bool
        error: str | None = None

    class DocumentOut(BaseModel):
        id: str
        title: str
        content: str
        url: str = ""
        category: str = ""
        metadata: dict = Field(default_factory=dict)
        created_at: str = ""

    class ChunkOut(BaseModel):
        id: str
        document_id: str
        content: str
        chunk_index: int
        sequence: int = 0
        content_hash: str = ""
        token_count: int = 0
        start_offset: int = 0
        end_offset: int = 0
        metadata: dict = Field(default_factory=dict)
        provenance: dict = Field(default_factory=dict)

        @model_validator(mode="before")
        @classmethod
        def _populate_sequence(cls, data: Any) -> Any:
            if isinstance(data, dict):
                if (
                    "sequence" not in data
                    or data["sequence"] is None
                    or data["sequence"] == 0
                ):
                    data["sequence"] = data.get("chunk_index", 0)
            elif hasattr(data, "chunk_index"):
                if not hasattr(data, "sequence") or getattr(data, "sequence", None) in (
                    None,
                    0,
                ):
                    setattr(data, "sequence", getattr(data, "chunk_index", 0))
            return data

    class SearchResultOut(BaseModel):
        chunk_id: str
        content: str
        score: float
        document_title: str = ""
        source: str = ""

    class ChatResponseOut(BaseModel):
        content: str
        model: str = ""
        provider: str = ""
        usage: dict = Field(default_factory=dict)

    class ToolDefinitionOut(BaseModel):
        name: str
        description: str
        input_schema: dict = Field(default_factory=dict)

    class ToolResultOut(BaseModel):
        tool_name: str
        output: Any = None
        error: str | None = None
        duration_ms: float | None = None

    class ResourceDefinitionOut(BaseModel):
        uri: str
        name: str
        description: str = ""
        mime_type: str | None = None

    class EntityOut(BaseModel):
        id: str
        label: str
        entity_type: str = ""
        properties: dict = Field(default_factory=dict)
        metadata: dict = Field(default_factory=dict)

    class RelationshipOut(BaseModel):
        id: str
        source_id: str
        target_id: str
        relation_type: str
        properties: dict = Field(default_factory=dict)
        confidence: float = 1.0
        metadata: dict = Field(default_factory=dict)

    class QueueItemOut(BaseModel):
        id: str
        payload: dict = Field(default_factory=dict)
        enqueued_at: float = 0.0
        worker_id: str | None = None

    # ── Top-level response models ────────────────────────────────────

    class HealthBackends(BaseModel):
        storage: str
        queue: str
        secrets: str
        embedding: str
        search: str
        graph: str
        llm: str
        consensus: str
        tools: str
        resources: str
        router: str

    class HealthResponse(BaseModel):
        status: str
        backends: HealthBackends

    class ReadinessResponse(BaseModel):
        status: str
        checks: dict[str, BackendCheckResult]

    class KnowledgeStatsResponse(BaseModel):
        documents: int
        chunks: int
        embeddings: int

    class ListDocumentsResponse(BaseModel):
        documents: list[DocumentOut]
        limit: int
        offset: int

    class StoreDocumentResponse(BaseModel):
        id: str
        stored: bool

    class PendingChunksResponse(BaseModel):
        chunks: list[ChunkOut]
        count: int

    class GetChunksResponse(BaseModel):
        chunks: list[ChunkOut]
        count: int

    class StoreChunksResponse(BaseModel):
        stored: int
        total: int

    class StoreEmbeddingsResponse(BaseModel):
        stored: int
        total: int

    class TextSearchResponse(BaseModel):
        results: list[SearchResultOut]
        query: str

    class SemanticSearchResponse(BaseModel):
        results: list[SearchResultOut]

    class HybridSearchResponse(BaseModel):
        results: list[SearchResultOut]

    class ListSecretsResponse(BaseModel):
        secrets: list[str]

    class SecretMetadataResponse(BaseModel):
        name: str
        exists: bool

    class GetSecretResponse(BaseModel):
        name: str
        value: str

    class ListModelsResponse(BaseModel):
        models: list[str]
        count: int

    class GatherResponse(BaseModel):
        responses: list[ChatResponseOut]
        count: int
        failed_models: list[str]
        models_queried: list[str]

    class SynthesizeResponse(BaseModel):
        synthesis: ChatResponseOut
        worker_responses: list[ChatResponseOut]
        failed_models: list[str]
        arbiter_attempted: bool
        arbiter_error: str | None

    class ListToolsResponse(BaseModel):
        tools: list[ToolDefinitionOut]
        count: int

    class CallToolResponse(BaseModel):
        tool_name: str
        output: Any = None
        error: str | None = None
        duration_ms: float | None = None

    class ListResourcesResponse(BaseModel):
        resources: list[ResourceDefinitionOut]
        count: int

    class ReadResourceResponse(BaseModel):
        uri: str
        content: str
        mime_type: str
        encoding: str

    class IdResponse(BaseModel):
        id: str

    class EntityResponse(BaseModel):
        id: str
        label: str
        entity_type: str = ""
        properties: dict = Field(default_factory=dict)
        metadata: dict = Field(default_factory=dict)

    class RelationshipsResponse(BaseModel):
        relationships: list[RelationshipOut]

    class QueueStatusResponse(BaseModel):
        pending: int
        processing: int
        dead_letter: int

    class EnqueueResponse(BaseModel):
        enqueued: int

    class FetchResponse(BaseModel):
        items: list[QueueItemOut]
        count: int

    class CompleteResponse(BaseModel):
        completed: bool

    class RequeueResponse(BaseModel):
        requeued: int

    # ── Router (Thompson Sampling) models ───────────────────────────

    class RouterSelectRequest(BaseModel):
        task_type: str
        candidates: list[str] | None = None

    class RouterSelectResponse(BaseModel):
        model: str
        task_type: str

    class RouterOutcomeRequest(BaseModel):
        model: str
        task_type: str
        reward: float = Field(ge=0.0, le=1.0)

    class RouterOutcomeResponse(BaseModel):
        recorded: bool

    class RouterRegisterRequest(BaseModel):
        provider_name: str
        models: list[str]
        priority: int = 0

    class RouterRegisterResponse(BaseModel):
        provider_name: str
        models_registered: int

    class RouterProfileRequest(BaseModel):
        model: str
        capabilities: list[str] = Field(default_factory=list)
        strengths: dict[str, float] = Field(default_factory=dict)

    class RouterProfileResponse(BaseModel):
        model: str
        capabilities: list[str]

    class RouterPerformanceResponse(BaseModel):
        arms: dict[str, dict]

    class RouterModelsResponse(BaseModel):
        models: list[dict]
        count: int

    class RouterHealthResponse(BaseModel):
        providers: dict[str, dict]

except ImportError:  # pydantic not installed (server extra not required)
    pass


_NOT_FOUND_RESPONSES: dict = {404: {"description": "Not found"}}


def _extract_chunk_content(chunk_data: object) -> str:
    """Extract text content from a chunk that may be a string or dict."""
    if isinstance(chunk_data, str):
        return chunk_data
    if isinstance(chunk_data, dict):
        return chunk_data.get("content", "")
    return ""
