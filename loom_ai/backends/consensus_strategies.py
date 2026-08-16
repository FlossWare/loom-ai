"""Consensus strategies, response caching, and disagreement detection.

Extends :class:`~loom_ai.consensus.ConsensusEngine` with pluggable
strategies for combining multiple model responses into a single
consensus result.

Strategies
----------
- **MajorityVoteStrategy** -- picks the response that the most models
  agree with (textual similarity via token overlap).
- **WeightedConsensusStrategy** -- scores responses using per-model
  weights and selects the highest-scoring one.
- **QualityThresholdStrategy** -- filters responses below a minimum
  quality score before selecting by highest score.

Extras
------
- **DisagreementDetector** -- flags when model responses diverge
  significantly (low pairwise similarity).
- **ConsensusCache** -- LRU cache keyed by prompt hash to avoid
  redundant consensus rounds.

Zero external dependencies -- uses only the standard library.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

from loom_ai.models import ChatResponse

logger = logging.getLogger(__name__)

_EMPTY_RESPONSES_MSG = "Cannot reach consensus with zero responses"


# ── Data types ─────────────────────────────────────────────────────────


@dataclass
class ConsensusOutcome:
    """Result from a consensus strategy evaluation.

    Attributes
    ----------
    selected:
        The winning response.
    strategy:
        Name of the strategy that produced this outcome.
    scores:
        Per-response scores (index-aligned with the input list).
    metadata:
        Strategy-specific details (e.g. vote counts, weight map).
    """

    selected: ChatResponse
    strategy: str
    scores: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DisagreementReport:
    """Summary of inter-model disagreement analysis.

    Attributes
    ----------
    is_disagreement:
        ``True`` when the average pairwise similarity falls below the
        configured threshold.
    average_similarity:
        Mean of all pairwise similarity scores in ``[0, 1]``.
    pairwise_scores:
        Flat list of ``(model_a, model_b, similarity)`` tuples.
    threshold:
        The threshold used for this analysis.
    """

    is_disagreement: bool
    average_similarity: float
    pairwise_scores: list[tuple[str, str, float]] = field(default_factory=list)
    threshold: float = 0.5


# ── Helpers ────────────────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Lowercase whitespace tokenizer for similarity comparison."""
    return set(text.lower().split())


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


# ── Abstract strategy ─────────────────────────────────────────────────


@runtime_checkable
class ResponseConsensusStrategy(Protocol):
    """Protocol for consensus strategies.

    Implementations provide :meth:`select` which receives the model
    responses and returns a :class:`ConsensusOutcome`.
    """

    def select(self, responses: Sequence[ChatResponse]) -> ConsensusOutcome:
        """Choose a single consensus response from *responses*.

        Raises :class:`ValueError` if *responses* is empty.
        """
        ...


# ── Strategies ─────────────────────────────────────────────────────────


class MajorityVoteStrategy:
    """Select the response most similar to the majority.

    For each response, compute average Jaccard similarity to all other
    responses.  The response with the highest average similarity wins
    -- it is the one the "majority" most agrees with.
    """

    def select(self, responses: Sequence[ChatResponse]) -> ConsensusOutcome:
        if not responses:
            raise ValueError(_EMPTY_RESPONSES_MSG)
        if len(responses) == 1:
            return ConsensusOutcome(
                selected=responses[0],
                strategy="majority_vote",
                scores=[1.0],
                metadata={"votes": {responses[0].model: 1}},
            )

        token_sets = [_tokenize(r.content) for r in responses]
        avg_sims: list[float] = []
        for i, ts_i in enumerate(token_sets):
            sims = [_jaccard(ts_i, ts_j) for j, ts_j in enumerate(token_sets) if j != i]
            avg_sims.append(sum(sims) / len(sims) if sims else 0.0)

        best_idx = max(range(len(avg_sims)), key=lambda i: avg_sims[i])
        return ConsensusOutcome(
            selected=responses[best_idx],
            strategy="majority_vote",
            scores=avg_sims,
            metadata={
                "winner_index": best_idx,
                "winner_model": responses[best_idx].model,
            },
        )


class WeightedConsensusStrategy:
    """Select the response with the highest model weight.

    Parameters
    ----------
    weights:
        Mapping from model id to numeric weight.  Models not present
        in the map receive ``default_weight``.
    default_weight:
        Weight assigned to unknown models (default ``1.0``).
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        *,
        default_weight: float = 1.0,
    ) -> None:
        self._weights = dict(weights) if weights else {}
        self._default_weight = default_weight

    def select(self, responses: Sequence[ChatResponse]) -> ConsensusOutcome:
        if not responses:
            raise ValueError(_EMPTY_RESPONSES_MSG)

        scores = [self._weights.get(r.model, self._default_weight) for r in responses]
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        return ConsensusOutcome(
            selected=responses[best_idx],
            strategy="weighted",
            scores=scores,
            metadata={
                "weights_used": {r.model: s for r, s in zip(responses, scores)},
                "winner_index": best_idx,
            },
        )


class QualityThresholdStrategy:
    """Filter by quality then select the highest-scoring response.

    Quality is estimated as the average Jaccard similarity of each
    response to all others (i.e. how well each agrees with the group).
    Responses below *min_quality* are discarded before selection.

    Parameters
    ----------
    min_quality:
        Minimum quality score in ``[0, 1]``.  Responses below this
        threshold are excluded.
    """

    def __init__(self, *, min_quality: float = 0.3) -> None:
        if not 0.0 <= min_quality <= 1.0:
            raise ValueError("min_quality must be between 0.0 and 1.0")
        self._min_quality = min_quality

    def select(self, responses: Sequence[ChatResponse]) -> ConsensusOutcome:
        if not responses:
            raise ValueError(_EMPTY_RESPONSES_MSG)

        if len(responses) == 1:
            return ConsensusOutcome(
                selected=responses[0],
                strategy="quality_threshold",
                scores=[1.0],
                metadata={"min_quality": self._min_quality, "filtered_count": 0},
            )

        token_sets = [_tokenize(r.content) for r in responses]
        scores: list[float] = []
        for i, ts_i in enumerate(token_sets):
            sims = [_jaccard(ts_i, ts_j) for j, ts_j in enumerate(token_sets) if j != i]
            scores.append(sum(sims) / len(sims) if sims else 0.0)

        # Filter by threshold.
        qualified = [
            (i, scores[i])
            for i in range(len(responses))
            if scores[i] >= self._min_quality
        ]

        if not qualified:
            # Fall back to best available even if below threshold.
            best_idx = max(range(len(scores)), key=lambda i: scores[i])
            return ConsensusOutcome(
                selected=responses[best_idx],
                strategy="quality_threshold",
                scores=scores,
                metadata={
                    "min_quality": self._min_quality,
                    "filtered_count": len(responses),
                    "fallback": True,
                },
            )

        best_idx = max(qualified, key=lambda pair: pair[1])[0]
        filtered_count = len(responses) - len(qualified)
        return ConsensusOutcome(
            selected=responses[best_idx],
            strategy="quality_threshold",
            scores=scores,
            metadata={
                "min_quality": self._min_quality,
                "filtered_count": filtered_count,
            },
        )


# ── Disagreement detection ─────────────────────────────────────────────


class DisagreementDetector:
    """Detect when model responses diverge significantly.

    Computes pairwise Jaccard similarity across all responses and
    flags disagreement when the average drops below *threshold*.

    Parameters
    ----------
    threshold:
        Average pairwise similarity below which disagreement is
        flagged (default ``0.5``).
    """

    def __init__(self, *, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        self._threshold = threshold

    def analyze(self, responses: Sequence[ChatResponse]) -> DisagreementReport:
        """Analyze *responses* for inter-model disagreement."""
        if len(responses) < 2:
            return DisagreementReport(
                is_disagreement=False,
                average_similarity=1.0,
                threshold=self._threshold,
            )

        token_sets = [_tokenize(r.content) for r in responses]
        pairwise: list[tuple[str, str, float]] = []
        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                sim = _jaccard(token_sets[i], token_sets[j])
                pairwise.append((responses[i].model, responses[j].model, sim))

        avg_sim = sum(s for _, _, s in pairwise) / len(pairwise) if pairwise else 1.0
        return DisagreementReport(
            is_disagreement=avg_sim < self._threshold,
            average_similarity=avg_sim,
            pairwise_scores=pairwise,
            threshold=self._threshold,
        )


# ── Response caching ───────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    """Internal cache entry with TTL tracking."""

    outcome: ConsensusOutcome
    created_at: float


class ConsensusCache:
    """Thread-safe LRU cache for consensus results keyed by prompt hash.

    Parameters
    ----------
    max_size:
        Maximum number of cached entries (default ``256``).
    ttl_seconds:
        Time-to-live for each entry in seconds (default ``300``).
        Entries older than this are evicted on access.
    """

    def __init__(
        self,
        *,
        max_size: int = 256,
        ttl_seconds: float = 300.0,
    ) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def hash_prompt(prompt: str, models: Sequence[str]) -> str:
        """Deterministic SHA-256 hash for a prompt + model set."""
        key_material = prompt + "\x00" + ",".join(sorted(models))
        return hashlib.sha256(key_material.encode()).hexdigest()

    def get(self, key: str) -> ConsensusOutcome | None:
        """Return a cached outcome, or ``None`` on miss / expiry."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if (time.monotonic() - entry.created_at) > self._ttl:
                self._store.pop(key, None)
                return None
            # Move to end (most-recently used).
            self._store.move_to_end(key)
            return entry.outcome

    def put(self, key: str, outcome: ConsensusOutcome) -> None:
        """Store an outcome, evicting the oldest entry if at capacity."""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = _CacheEntry(
                    outcome=outcome,
                    created_at=time.monotonic(),
                )
            else:
                if len(self._store) >= self._max_size:
                    self._store.popitem(last=False)
                self._store[key] = _CacheEntry(
                    outcome=outcome,
                    created_at=time.monotonic(),
                )

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
