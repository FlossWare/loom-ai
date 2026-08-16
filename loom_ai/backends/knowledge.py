"""RAG chunking and knowledge pipeline backends for loom-ai.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
TokenChunker               -- sentence-based text chunker with overlap
InMemoryKnowledgePipeline  -- keyword-scored retrieval over chunked documents
"""

from __future__ import annotations

import re
import uuid

from loom_ai.models_phase1 import RetrievalResult

# Characters-per-token estimate used to convert between character
# lengths and approximate token counts.
_CHARS_PER_TOKEN = 4


class TokenChunker:
    """Sentence-aware text chunker with token-bounded overlap.

    Satisfies :class:`~loom_ai.contracts_phase1.ChunkingStrategy` via
    structural subtyping.

    Sentences are split on ``". "`` and ``"\\n"``.  Each chunk accumulates
    sentences until the estimated token count would exceed *max_tokens*.
    Consecutive chunks share up to *overlap* tokens of trailing context
    from the previous chunk.
    """

    # Split on ". " or newline, keeping the delimiter attached to the
    # preceding sentence so that periods are not lost.
    _SPLIT_RE = re.compile(r"(?<=\. )|\n")

    def chunk(
        self,
        content: str,
        *,
        max_tokens: int = 512,
        overlap: int = 50,
    ) -> list[str]:
        """Split *content* into overlapping token-bounded chunks."""
        if not content:
            return []

        sentences = self._split_sentences(content)
        if not sentences:
            return []

        max_chars = max_tokens * _CHARS_PER_TOKEN
        overlap_chars = overlap * _CHARS_PER_TOKEN

        chunks: list[str] = []
        current_sentences: list[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)

            # If adding this sentence would exceed the budget and we
            # already have content, flush the current chunk.
            if current_sentences and current_len + sentence_len > max_chars:
                chunks.append("".join(current_sentences))

                # Build overlap prefix from the tail of the flushed chunk.
                current_sentences, current_len = self._build_overlap(
                    current_sentences, overlap_chars
                )

            current_sentences.append(sentence)
            current_len += sentence_len

        # Flush remaining content.
        if current_sentences:
            chunks.append("".join(current_sentences))

        return chunks

    # -- helpers ----------------------------------------------------------

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        """Split *text* into sentence-like segments.

        Empty segments are discarded, but whitespace within segments is
        preserved.
        """
        parts = cls._SPLIT_RE.split(text)
        return [p for p in parts if p]

    @staticmethod
    def _build_overlap(
        sentences: list[str],
        overlap_chars: int,
    ) -> tuple[list[str], int]:
        """Return trailing sentences that fit within *overlap_chars*.

        Returns ``(overlap_sentences, total_char_length)``.
        """
        if overlap_chars <= 0:
            return [], 0

        tail: list[str] = []
        total = 0
        for sentence in reversed(sentences):
            if total + len(sentence) > overlap_chars:
                break
            tail.append(sentence)
            total += len(sentence)

        tail.reverse()
        return tail, total


class InMemoryKnowledgePipeline:
    """In-memory RAG pipeline with keyword-frequency scoring.

    Satisfies :class:`~loom_ai.contracts_phase1.KnowledgePipeline` via
    structural subtyping.

    Parameters
    ----------
    chunker:
        A :class:`~loom_ai.contracts_phase1.ChunkingStrategy` used to
        split ingested content into chunks.
    max_tokens:
        Default token budget passed to the chunker.
    overlap:
        Default overlap (in tokens) passed to the chunker.
    """

    def __init__(
        self,
        chunker: TokenChunker,
        *,
        max_tokens: int = 512,
        overlap: int = 50,
    ) -> None:
        self._chunker = chunker
        self._max_tokens = max_tokens
        self._overlap = overlap

        # doc_id -> list of chunk_ids
        self._documents: dict[str, list[str]] = {}
        # chunk_id -> chunk text
        self._chunks: dict[str, str] = {}
        # chunk_id -> doc_id
        self._chunk_to_doc: dict[str, str] = {}
        # chunk_id -> metadata dict
        self._chunk_metadata: dict[str, dict] = {}

    async def ingest(
        self,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> str:
        """Chunk *content* and store internally.  Return a document id."""
        doc_id = str(uuid.uuid4())
        pieces = self._chunker.chunk(
            content,
            max_tokens=self._max_tokens,
            overlap=self._overlap,
        )

        chunk_ids: list[str] = []
        for piece in pieces:
            chunk_id = str(uuid.uuid4())
            self._chunks[chunk_id] = piece
            self._chunk_to_doc[chunk_id] = doc_id
            self._chunk_metadata[chunk_id] = dict(metadata) if metadata else {}
            chunk_ids.append(chunk_id)

        self._documents[doc_id] = chunk_ids
        return doc_id

    async def query(
        self,
        question: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Score chunks by keyword occurrence and return the top *limit*."""
        words = _tokenize_query(question)
        if not words:
            return []

        scored: list[tuple[str, float]] = []
        for chunk_id, text in self._chunks.items():
            score = _keyword_score(text, words)
            if score > 0:
                scored.append((chunk_id, score))

        # Sort descending by score, then by chunk_id for determinism.
        scored.sort(key=lambda t: (-t[1], t[0]))

        results: list[RetrievalResult] = []
        for chunk_id, score in scored[:limit]:
            doc_id = self._chunk_to_doc[chunk_id]
            results.append(
                RetrievalResult(
                    content=self._chunks[chunk_id],
                    score=score,
                    source=doc_id,
                    chunk_id=chunk_id,
                    metadata=dict(self._chunk_metadata.get(chunk_id, {})),
                )
            )

        return results


# ── helpers ──────────────────────────────────────────────────────────────


def _tokenize_query(text: str) -> list[str]:
    """Lowercase and split query text into individual words."""
    return text.lower().split()


def _keyword_score(text: str, words: list[str]) -> float:
    """Count how many times *words* appear in *text* (case-insensitive)."""
    lower = text.lower()
    return float(sum(lower.count(w) for w in words))
