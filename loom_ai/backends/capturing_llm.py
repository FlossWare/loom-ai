"""LLM wrapper that auto-captures interactions into the knowledge base.

Implements :class:`~loom_ai.protocols.LLMBackend` by delegating to an
inner backend and recording each interaction for future recall.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loom_ai.contracts_phase1 import KnowledgePipeline, PersistentMemoryBackend
    from loom_ai.models import ChatMessage, ChatResponse


class CapturingLLMBackend:
    """Wraps any ``LLMBackend`` and stores each interaction.

    Captured data is forwarded to an optional ``KnowledgePipeline``
    (for RAG retrieval) and/or ``PersistentMemoryBackend`` (for named
    recall).  The wrapper is transparent: callers see the same
    ``chat`` / ``chat_stream`` / ``list_models`` interface.
    """

    def __init__(
        self,
        inner: Any,
        *,
        knowledge: KnowledgePipeline | None = None,
        memory: PersistentMemoryBackend | None = None,
    ) -> None:
        self._inner = inner
        self._knowledge = knowledge
        self._memory = memory

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        start = time.monotonic()
        response = await self._inner.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        await self._capture(
            messages, response.content, model=model, latency_ms=elapsed_ms
        )
        return response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        chunks: list[str] = []
        start = time.monotonic()
        async for chunk in self._inner.chat_stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        ):
            chunks.append(chunk)
            yield chunk
        elapsed_ms = (time.monotonic() - start) * 1000

        full_response = "".join(chunks)
        await self._capture(messages, full_response, model=model, latency_ms=elapsed_ms)

    async def list_models(self) -> list[str]:
        return await self._inner.list_models()

    async def _capture(
        self,
        messages: list[ChatMessage],
        response_content: str,
        *,
        model: str | None = None,
        latency_ms: float = 0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        prompt_text = "\n".join(
            f"[{getattr(m, 'role', 'user')}] {getattr(m, 'content', str(m))}"
            for m in messages
        )
        interaction_text = f"Prompt:\n{prompt_text}\n\nResponse:\n{response_content}"

        if self._knowledge is not None:
            try:
                await self._knowledge.ingest(
                    interaction_text,
                    metadata={
                        "type": "llm_interaction",
                        "model": model or "unknown",
                        "timestamp": now,
                        "latency_ms": round(latency_ms, 1),
                    },
                )
            except Exception:
                pass

        if self._memory is not None:
            try:
                name = f"llm-interaction-{now}"
                await self._memory.store(
                    name,
                    interaction_text,
                    memory_type="interaction",
                    metadata={
                        "model": model or "unknown",
                        "latency_ms": round(latency_ms, 1),
                    },
                )
            except Exception:
                pass
