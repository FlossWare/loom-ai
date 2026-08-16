"""Tests for loom_ai.backends.consensus_strategies."""

import time

import pytest

from loom_ai.backends.consensus_strategies import (
    ConsensusCache,
    ConsensusOutcome,
    DisagreementDetector,
    MajorityVoteStrategy,
    QualityThresholdStrategy,
    WeightedConsensusStrategy,
    _jaccard,
    _tokenize,
)
from loom_ai.models import ChatResponse

# ── Helpers ────────────────────────────────────────────────────────────


def _resp(content: str, model: str = "test") -> ChatResponse:
    return ChatResponse(content=content, model=model, provider="fake")


# ── Tokenizer / Jaccard tests ─────────────────────────────────────────


def test_tokenize_basic():
    tokens = _tokenize("Hello World hello")
    assert tokens == {"hello", "world"}


def test_jaccard_identical():
    assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint():
    assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial():
    sim = _jaccard({"a", "b", "c"}, {"a", "b", "d"})
    assert sim == pytest.approx(2 / 4)


def test_jaccard_empty_sets():
    assert _jaccard(set(), set()) == 1.0


# ── MajorityVoteStrategy ──────────────────────────────────────────────


class TestMajorityVote:
    def test_single_response(self):
        strategy = MajorityVoteStrategy()
        outcome = strategy.select([_resp("hello world", "m1")])
        assert outcome.selected.model == "m1"
        assert outcome.strategy == "majority_vote"

    def test_empty_raises(self):
        strategy = MajorityVoteStrategy()
        with pytest.raises(ValueError, match="zero responses"):
            strategy.select([])

    def test_majority_wins(self):
        """The response most similar to others should win."""
        strategy = MajorityVoteStrategy()
        responses = [
            _resp("the cat sat on the mat", "m1"),
            _resp("the cat sat on the mat today", "m2"),
            _resp("completely unrelated different text here", "m3"),
        ]
        outcome = strategy.select(responses)
        # m1 and m2 are similar; m3 is different. Winner should be m1 or m2.
        assert outcome.selected.model in ("m1", "m2")
        assert len(outcome.scores) == 3

    def test_identical_responses(self):
        strategy = MajorityVoteStrategy()
        responses = [
            _resp("same text", "m1"),
            _resp("same text", "m2"),
            _resp("same text", "m3"),
        ]
        outcome = strategy.select(responses)
        # All have perfect similarity.
        assert all(s == pytest.approx(1.0) for s in outcome.scores)


# ── WeightedConsensusStrategy ─────────────────────────────────────────


class TestWeightedConsensus:
    def test_highest_weight_wins(self):
        strategy = WeightedConsensusStrategy(weights={"m1": 1.0, "m2": 5.0, "m3": 2.0})
        responses = [
            _resp("r1", "m1"),
            _resp("r2", "m2"),
            _resp("r3", "m3"),
        ]
        outcome = strategy.select(responses)
        assert outcome.selected.model == "m2"
        assert outcome.strategy == "weighted"
        assert outcome.scores == [1.0, 5.0, 2.0]

    def test_default_weight(self):
        strategy = WeightedConsensusStrategy(
            weights={"m1": 3.0},
            default_weight=10.0,
        )
        responses = [
            _resp("r1", "m1"),
            _resp("r2", "unknown"),
        ]
        outcome = strategy.select(responses)
        assert outcome.selected.model == "unknown"
        assert outcome.scores == [3.0, 10.0]

    def test_empty_raises(self):
        strategy = WeightedConsensusStrategy()
        with pytest.raises(ValueError, match="zero responses"):
            strategy.select([])

    def test_no_weights_uses_default(self):
        strategy = WeightedConsensusStrategy()
        responses = [_resp("r1", "m1"), _resp("r2", "m2")]
        outcome = strategy.select(responses)
        assert outcome.scores == [1.0, 1.0]
        # First one wins on tie.
        assert outcome.selected.model == "m1"


# ── QualityThresholdStrategy ──────────────────────────────────────────


class TestQualityThreshold:
    def test_single_response(self):
        strategy = QualityThresholdStrategy(min_quality=0.5)
        outcome = strategy.select([_resp("hello", "m1")])
        assert outcome.selected.model == "m1"
        assert outcome.strategy == "quality_threshold"

    def test_empty_raises(self):
        strategy = QualityThresholdStrategy()
        with pytest.raises(ValueError, match="zero responses"):
            strategy.select([])

    def test_filters_outlier(self):
        strategy = QualityThresholdStrategy(min_quality=0.1)
        responses = [
            _resp("the cat sat on the mat", "m1"),
            _resp("the cat sat on the mat today", "m2"),
            _resp("xyzzy completely unrelated gibberish foo", "m3"),
        ]
        outcome = strategy.select(responses)
        # m1 and m2 are similar; m3 is the outlier.
        assert outcome.selected.model in ("m1", "m2")

    def test_fallback_when_all_below_threshold(self):
        strategy = QualityThresholdStrategy(min_quality=0.99)
        responses = [
            _resp("cats are great", "m1"),
            _resp("dogs are better", "m2"),
            _resp("fish are cool", "m3"),
        ]
        outcome = strategy.select(responses)
        # All are below threshold; should still return something.
        assert outcome.selected is not None
        assert outcome.metadata.get("fallback") is True

    def test_invalid_min_quality(self):
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            QualityThresholdStrategy(min_quality=1.5)


# ── DisagreementDetector ──────────────────────────────────────────────


class TestDisagreementDetector:
    def test_single_response_no_disagreement(self):
        detector = DisagreementDetector()
        report = detector.analyze([_resp("hello", "m1")])
        assert not report.is_disagreement
        assert report.average_similarity == 1.0

    def test_identical_no_disagreement(self):
        detector = DisagreementDetector(threshold=0.5)
        responses = [
            _resp("same text here", "m1"),
            _resp("same text here", "m2"),
        ]
        report = detector.analyze(responses)
        assert not report.is_disagreement
        assert report.average_similarity == pytest.approx(1.0)

    def test_divergent_triggers_disagreement(self):
        detector = DisagreementDetector(threshold=0.5)
        responses = [
            _resp("alpha bravo charlie", "m1"),
            _resp("xray yankee zulu", "m2"),
            _resp("one two three", "m3"),
        ]
        report = detector.analyze(responses)
        assert report.is_disagreement
        assert report.average_similarity < 0.5

    def test_pairwise_scores_populated(self):
        detector = DisagreementDetector()
        responses = [
            _resp("a b c", "m1"),
            _resp("a b d", "m2"),
            _resp("e f g", "m3"),
        ]
        report = detector.analyze(responses)
        # 3 responses -> 3 pairwise comparisons.
        assert len(report.pairwise_scores) == 3

    def test_invalid_threshold(self):
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            DisagreementDetector(threshold=-0.1)


# ── ConsensusCache ─────────────────────────────────────────────────────


class TestConsensusCache:
    def test_put_and_get(self):
        cache = ConsensusCache(max_size=10, ttl_seconds=60)
        outcome = ConsensusOutcome(
            selected=_resp("cached", "m1"),
            strategy="test",
        )
        key = ConsensusCache.hash_prompt("hello", ["m1", "m2"])
        cache.put(key, outcome)
        assert cache.get(key) is outcome
        assert len(cache) == 1

    def test_miss_returns_none(self):
        cache = ConsensusCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self, monkeypatch):
        cache = ConsensusCache(ttl_seconds=0.01)
        outcome = ConsensusOutcome(
            selected=_resp("old", "m1"),
            strategy="test",
        )
        cache.put("key1", outcome)
        # Simulate time passing.
        time.sleep(0.02)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = ConsensusCache(max_size=2, ttl_seconds=300)
        o1 = ConsensusOutcome(selected=_resp("1", "m1"), strategy="t")
        o2 = ConsensusOutcome(selected=_resp("2", "m2"), strategy="t")
        o3 = ConsensusOutcome(selected=_resp("3", "m3"), strategy="t")
        cache.put("k1", o1)
        cache.put("k2", o2)
        # k1 should be evicted when k3 is added.
        cache.put("k3", o3)
        assert cache.get("k1") is None
        assert cache.get("k2") is o2
        assert cache.get("k3") is o3

    def test_clear(self):
        cache = ConsensusCache()
        cache.put("k1", ConsensusOutcome(selected=_resp("x", "m"), strategy="t"))
        cache.clear()
        assert len(cache) == 0
        assert cache.get("k1") is None

    def test_hash_deterministic(self):
        h1 = ConsensusCache.hash_prompt("hello", ["m1", "m2"])
        h2 = ConsensusCache.hash_prompt("hello", ["m2", "m1"])
        assert h1 == h2  # Sorted internally.

    def test_hash_different_prompts(self):
        h1 = ConsensusCache.hash_prompt("hello", ["m1"])
        h2 = ConsensusCache.hash_prompt("world", ["m1"])
        assert h1 != h2

    def test_update_existing_key(self):
        cache = ConsensusCache(max_size=10, ttl_seconds=60)
        o1 = ConsensusOutcome(selected=_resp("old", "m1"), strategy="t")
        o2 = ConsensusOutcome(selected=_resp("new", "m1"), strategy="t")
        cache.put("k1", o1)
        cache.put("k1", o2)
        assert cache.get("k1") is o2
        assert len(cache) == 1
