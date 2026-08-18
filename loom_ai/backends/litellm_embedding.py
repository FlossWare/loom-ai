"""LiteLLM embedding backend (requires ``litellm`` extra).

Wraps LiteLLM's embedding API behind the
:class:`~loom_ai.protocols.EmbeddingBackend` protocol, providing access
to 100+ embedding providers through a unified interface.
"""

from __future__ import annotations

try:
    import litellm  # type: ignore[import-untyped]
except ImportError as _exc:
    raise ImportError(
        "LiteLLM embeddings require the 'litellm' package.  "
        "Install with: pip install flossware-loom-ai[litellm]"
    ) from _exc


class LiteLLMEmbeddingBackend:
    """LiteLLM-backed embedding generation.

    Satisfies :class:`~loom_ai.protocols.EmbeddingBackend` via structural
    subtyping.
    """

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ) -> None:
        self._model = model
        self._dimensions = dimensions

    @classmethod
    async def from_env(cls) -> LiteLLMEmbeddingBackend:
        """Build from environment — LiteLLM reads provider keys automatically."""
        return cls()

    async def embed_single(self, text: str) -> list[float]:
        resp = await litellm.aembedding(
            model=self._model, input=[text], dimensions=self._dimensions,
        )
        if not resp.data:
            raise RuntimeError("Embedding API returned no data")
        return resp.data[0]["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = await litellm.aembedding(
            model=self._model, input=texts, dimensions=self._dimensions,
        )
        return [item["embedding"] for item in resp.data]

    @property
    def dimension(self) -> int:
        return self._dimensions
