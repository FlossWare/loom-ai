"""OpenAI embedding backend (requires ``openai`` extra).

Wraps the OpenAI embeddings API behind the
:class:`~loom_ai.protocols.EmbeddingBackend` protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import openai  # type: ignore[import-untyped]
except ImportError as _exc:
    raise ImportError(
        "OpenAI embeddings require the 'openai' package.  "
        "Install with: pip install flossware-loom-ai[openai]"
    ) from _exc

if TYPE_CHECKING:
    pass


class OpenAIEmbeddingBackend:
    """OpenAI-backed embedding generation.

    Satisfies :class:`~loom_ai.protocols.EmbeddingBackend` via structural
    subtyping.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key or None)
        self._model = model
        self._dimensions = dimensions

    @classmethod
    async def from_env(cls) -> OpenAIEmbeddingBackend:
        """Build from ``OPENAI_API_KEY`` environment variable."""
        import os

        return cls(api_key=os.environ.get("OPENAI_API_KEY", ""))

    async def embed_single(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions,
        )
        if not resp.data:
            raise RuntimeError("Embedding API returned no data")
        return resp.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        return [item.embedding for item in resp.data]

    @property
    def dimension(self) -> int:
        return self._dimensions
