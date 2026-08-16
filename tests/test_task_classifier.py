"""Tests for the rule-based task classifier.

Covers protocol conformance, classification accuracy for each built-in
category, fallback to ``simple_qa``, custom rule injection, and
blueprint field correctness.
"""

from __future__ import annotations

import re

from loom_ai.backends.task_classifier import (
    ExecutionBlueprint,
    RuleBasedTaskClassifier,
    TaskClassifier,
)

# -- Protocol conformance -------------------------------------------------


def test_rule_based_classifier_conformance():
    """RuleBasedTaskClassifier satisfies the TaskClassifier protocol."""
    assert isinstance(RuleBasedTaskClassifier(), TaskClassifier)


# -- Classification accuracy ----------------------------------------------


def test_classify_consensus():
    """Tasks mentioning consensus keywords are classified as consensus."""
    tc = RuleBasedTaskClassifier()
    for prompt in [
        "Use multi-model consensus to verify this",
        "Let the models vote on the best answer",
        "debate the merits of each approach",
    ]:
        bp = tc.classify(prompt)
        assert bp.category == "consensus", f"Expected consensus for: {prompt!r}"
        assert bp.use_consensus is True


def test_classify_code_generation():
    """Tasks mentioning code keywords are classified as code_generation."""
    tc = RuleBasedTaskClassifier()
    for prompt in [
        "Write a Python function to parse JSON",
        "Generate a REST client class",
        "Refactor this module for clarity",
        "Implement a binary search",
    ]:
        bp = tc.classify(prompt)
        assert bp.category == "code_generation", (
            f"Expected code_generation for: {prompt!r}"
        )


def test_classify_research():
    """Tasks mentioning research keywords are classified as research."""
    tc = RuleBasedTaskClassifier()
    for prompt in [
        "Research the best caching strategies",
        "Investigate why latency spiked",
        "Compare Redis and Memcached",
        "Analyse the performance data",
    ]:
        bp = tc.classify(prompt)
        assert bp.category == "research", f"Expected research for: {prompt!r}"


def test_classify_summarization():
    """Tasks mentioning summary keywords are classified as summarization."""
    tc = RuleBasedTaskClassifier()
    for prompt in [
        "Summarize this document",
        "Give me a TL;DR of the report",
        "Condense the meeting notes",
    ]:
        bp = tc.classify(prompt)
        assert bp.category == "summarization", f"Expected summarization for: {prompt!r}"


def test_classify_translation():
    """Tasks mentioning translation keywords are classified as translation."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("Translate this paragraph to French")
    assert bp.category == "translation"


def test_classify_simple_qa_fallback():
    """Unmatched tasks fall back to simple_qa."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("What is the capital of France?")
    assert bp.category == "simple_qa"
    assert bp.use_consensus is False


# -- Rule priority ---------------------------------------------------------


def test_consensus_takes_priority_over_code():
    """Consensus keywords win when both consensus and code words appear."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("Use multi-model consensus to generate code")
    assert bp.category == "consensus"


# -- Blueprint fields ------------------------------------------------------


def test_blueprint_defaults():
    """ExecutionBlueprint has sensible defaults."""
    bp = ExecutionBlueprint(category="test")
    assert bp.category == "test"
    assert bp.models == []
    assert bp.use_consensus is False
    assert bp.timeout_seconds == 30.0
    assert bp.max_retries == 1
    assert bp.metadata == {}


def test_research_blueprint_fields():
    """Research blueprint has correct timeout and retry settings."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("Research distributed systems")
    assert bp.timeout_seconds == 60.0
    assert bp.max_retries == 2
    assert "fast" in bp.models


def test_code_generation_blueprint_fields():
    """Code generation blueprint uses balanced model."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("Implement a linked list")
    assert bp.timeout_seconds == 45.0
    assert "balanced" in bp.models


def test_consensus_blueprint_fields():
    """Consensus blueprint uses multiple models and consensus flag."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("Vote on the best approach")
    assert bp.use_consensus is True
    assert len(bp.models) >= 3
    assert bp.timeout_seconds == 90.0


def test_simple_qa_blueprint_fields():
    """Simple QA blueprint uses fast model with short timeout."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("Hello world")
    assert bp.timeout_seconds == 15.0
    assert bp.models == ["fast"]


# -- Custom rules ----------------------------------------------------------


def test_custom_rules():
    """Custom rules override the built-in set."""
    custom_rules = [
        (re.compile(r"\bfoo\b", re.IGNORECASE), "custom_category"),
    ]
    tc = RuleBasedTaskClassifier(rules=custom_rules)
    bp = tc.classify("Please foo this thing")
    assert bp.category == "custom_category"


def test_custom_defaults():
    """Custom defaults override blueprint settings per category."""
    custom_defaults = {
        "simple_qa": {
            "models": ["turbo"],
            "use_consensus": False,
            "timeout_seconds": 5.0,
            "max_retries": 0,
        },
    }
    tc = RuleBasedTaskClassifier(defaults=custom_defaults)
    bp = tc.classify("What is 2+2?")
    assert bp.category == "simple_qa"
    assert bp.models == ["turbo"]
    assert bp.timeout_seconds == 5.0
    assert bp.max_retries == 0


# -- Edge cases ------------------------------------------------------------


def test_empty_task_falls_back():
    """An empty task string falls back to simple_qa."""
    tc = RuleBasedTaskClassifier()
    bp = tc.classify("")
    assert bp.category == "simple_qa"


def test_case_insensitive_matching():
    """Classification is case-insensitive."""
    tc = RuleBasedTaskClassifier()
    assert tc.classify("RESEARCH something").category == "research"
    assert tc.classify("Consensus needed").category == "consensus"
    assert tc.classify("GENERATE a script").category == "code_generation"
