"""Tests for loom_ai.backends.learning.SimpleLearningExtractor."""

import pytest

from loom_ai.backends.learning import SimpleLearningExtractor
from loom_ai.contracts_workflow import LearningExtractor
from loom_ai.models import ChatMessage
from loom_ai.models_workflow import Learning

# ── Protocol conformance ─────────────────────────────────────────────────


def test_satisfies_protocol():
    """SimpleLearningExtractor satisfies the LearningExtractor protocol."""
    assert isinstance(SimpleLearningExtractor(), LearningExtractor)


# ── detect_feedback ──────────────────────────────────────────────────────


async def test_detect_correction_you_should_have():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="You should have used the fleet.")]
    signals = await ext.detect_feedback(msgs)
    assert len(signals) >= 1
    correction = [s for s in signals if s.type == "correction"]
    assert len(correction) == 1
    assert correction[0].confidence >= 0.8


async def test_detect_correction_thats_not_right():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="That's not right at all.")]
    signals = await ext.detect_feedback(msgs)
    types = {s.type for s in signals}
    assert "correction" in types


async def test_detect_correction_why_didnt_you():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Why didn't you use multi-AI?")]
    signals = await ext.detect_feedback(msgs)
    types = {s.type for s in signals}
    assert "correction" in types


async def test_detect_preference_always():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Always use the fleet for reviews.")]
    signals = await ext.detect_feedback(msgs)
    prefs = [s for s in signals if s.type == "preference"]
    assert len(prefs) == 1
    assert prefs[0].confidence >= 0.8


async def test_detect_preference_never():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Never skip tests.")]
    signals = await ext.detect_feedback(msgs)
    prefs = [s for s in signals if s.type == "preference"]
    assert len(prefs) == 1


async def test_detect_preference_dont():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Don't commit without review.")]
    signals = await ext.detect_feedback(msgs)
    prefs = [s for s in signals if s.type == "preference"]
    assert len(prefs) >= 1


async def test_detect_preference_prefer():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="I prefer TypeScript over JavaScript.")]
    signals = await ext.detect_feedback(msgs)
    prefs = [s for s in signals if s.type == "preference"]
    assert len(prefs) >= 1


async def test_detect_preference_avoid():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Avoid using global state.")]
    signals = await ext.detect_feedback(msgs)
    prefs = [s for s in signals if s.type == "preference"]
    assert len(prefs) >= 1


async def test_detect_confirmation_worked_well():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="That worked well, thanks!")]
    signals = await ext.detect_feedback(msgs)
    confirmations = [s for s in signals if s.type == "confirmation"]
    assert len(confirmations) == 1


async def test_detect_confirmation_good_job():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Good job on the refactor.")]
    signals = await ext.detect_feedback(msgs)
    confirmations = [s for s in signals if s.type == "confirmation"]
    assert len(confirmations) == 1


async def test_detect_confirmation_exactly_what_i_wanted():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="Exactly what I wanted!")]
    signals = await ext.detect_feedback(msgs)
    confirmations = [s for s in signals if s.type == "confirmation"]
    assert len(confirmations) == 1


async def test_no_feedback_in_neutral_message():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="user", content="What time is it?")]
    signals = await ext.detect_feedback(msgs)
    assert signals == []


async def test_ignores_assistant_messages():
    ext = SimpleLearningExtractor()
    msgs = [ChatMessage(role="assistant", content="You should have used the fleet.")]
    signals = await ext.detect_feedback(msgs)
    assert signals == []


async def test_multiple_messages_multiple_signals():
    ext = SimpleLearningExtractor()
    msgs = [
        ChatMessage(role="user", content="Always use multi-AI."),
        ChatMessage(role="user", content="That worked well."),
        ChatMessage(role="assistant", content="Noted."),
    ]
    signals = await ext.detect_feedback(msgs)
    types = {s.type for s in signals}
    assert "preference" in types
    assert "confirmation" in types
    assert len(signals) == 2


async def test_one_signal_per_type_per_message():
    """A single message produces at most one signal per feedback type."""
    ext = SimpleLearningExtractor()
    msgs = [
        ChatMessage(
            role="user",
            content="Always use fleet and never skip review.",
        )
    ]
    signals = await ext.detect_feedback(msgs)
    prefs = [s for s in signals if s.type == "preference"]
    # Both "always" and "never" are preference patterns, but we emit at
    # most one preference signal per message.
    assert len(prefs) == 1


async def test_feedback_signal_source_message():
    ext = SimpleLearningExtractor()
    original = "You should have tested first."
    msgs = [ChatMessage(role="user", content=original)]
    signals = await ext.detect_feedback(msgs)
    assert signals[0].source_message == original


# ── record_experience ────────────────────────────────────────────────────


async def test_record_experience_returns_uuid():
    ext = SimpleLearningExtractor()
    eid = await ext.record_experience("deploy service", "success")
    # UUID4 is 36 characters with hyphens
    assert len(eid) == 36
    assert eid.count("-") == 4


async def test_record_experience_unique_ids():
    ext = SimpleLearningExtractor()
    id1 = await ext.record_experience("task-a", "ok")
    id2 = await ext.record_experience("task-b", "ok")
    assert id1 != id2


async def test_record_experience_with_context():
    ext = SimpleLearningExtractor()
    ctx = {"model": "opus", "duration_ms": 1200}
    eid = await ext.record_experience("review code", "passed", context=ctx)
    assert eid  # non-empty
    # Verify context is stored by extracting learnings (smoke test).
    learnings = await ext.extract_learnings(eid)
    assert len(learnings) >= 1


# ── extract_learnings ────────────────────────────────────────────────────


async def test_extract_learnings_from_key_phrases():
    ext = SimpleLearningExtractor()
    eid = await ext.record_experience(
        "implement auth module",
        "use JWT tokens. apply rate limiting.",
    )
    learnings = await ext.extract_learnings(eid)
    assert len(learnings) >= 2
    contents = [ln.content.lower() for ln in learnings]
    assert any("use jwt tokens" in c for c in contents)
    assert any("apply rate limiting" in c for c in contents)


async def test_extract_learnings_returns_learning_objects():
    ext = SimpleLearningExtractor()
    eid = await ext.record_experience("fix bug", "check edge cases.")
    learnings = await ext.extract_learnings(eid)
    for ln in learnings:
        assert isinstance(ln, Learning)
        assert ln.source_experience == eid
        assert ln.id  # non-empty UUID
        assert ln.created_at  # ISO timestamp


async def test_extract_learnings_fallback_summary():
    """When no key phrases are found, a summary learning is returned."""
    ext = SimpleLearningExtractor()
    eid = await ext.record_experience("small task", "ok")
    learnings = await ext.extract_learnings(eid)
    assert len(learnings) == 1
    assert learnings[0].category == "summary"
    assert "small task" in learnings[0].content


async def test_extract_learnings_unknown_experience():
    ext = SimpleLearningExtractor()
    learnings = await ext.extract_learnings("nonexistent-id")
    assert learnings == []


# ── update_strategy ──────────────────────────────────────────────────────


async def test_update_strategy_tracks_reward():
    ext = SimpleLearningExtractor()
    await ext.update_strategy("multi-ai", "success", reward=0.9)
    state = ext._strategies["multi-ai"]
    assert state["total_trials"] == 1
    assert state["total_reward"] == pytest.approx(0.9)


async def test_update_strategy_accumulates():
    ext = SimpleLearningExtractor()
    await ext.update_strategy("solo", "fail", reward=0.2)
    await ext.update_strategy("solo", "success", reward=0.8)
    await ext.update_strategy("solo", "success", reward=0.7)
    state = ext._strategies["solo"]
    assert state["total_trials"] == 3
    assert state["total_reward"] == pytest.approx(1.7)


async def test_update_strategy_alpha_beta():
    ext = SimpleLearningExtractor()
    # reward >= 0.5 -> alpha incremented
    await ext.update_strategy("strat-a", "success", reward=0.9)
    state = ext._strategies["strat-a"]
    assert state["alpha"] == 2.0  # initial 1.0 + 1.0
    assert state["beta"] == 1.0  # unchanged

    # reward < 0.5 -> beta incremented
    await ext.update_strategy("strat-a", "fail", reward=0.1)
    state = ext._strategies["strat-a"]
    assert state["alpha"] == 2.0
    assert state["beta"] == 2.0


async def test_update_strategy_multiple_strategies():
    ext = SimpleLearningExtractor()
    await ext.update_strategy("fast", "success", reward=0.8)
    await ext.update_strategy("thorough", "success", reward=0.6)
    assert "fast" in ext._strategies
    assert "thorough" in ext._strategies
    assert ext._strategies["fast"]["total_trials"] == 1
    assert ext._strategies["thorough"]["total_trials"] == 1
