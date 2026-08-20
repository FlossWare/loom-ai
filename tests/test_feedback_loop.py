"""Tests for the SimpleFeedbackLoopDetector backend."""

from loom_ai.backends.feedback_loop import SimpleFeedbackLoopDetector
from loom_ai.contracts_session import FeedbackLoopDetector
from loom_ai.models_session import FeedbackLoopReport


def test_satisfies_protocol():
    """SimpleFeedbackLoopDetector structurally matches the protocol."""
    detector = SimpleFeedbackLoopDetector()
    assert isinstance(detector, FeedbackLoopDetector)


async def test_healthy_system():
    """Evenly distributed usage produces no risks."""
    data = [
        {"model": "gpt-4o", "role": "generator"},
        {"model": "claude-opus", "role": "generator"},
        {"model": "gemini-pro", "role": "evaluator"},
        {"model": "llama-3", "role": "evaluator"},
    ]
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    report = await detector.analyze()

    assert isinstance(report, FeedbackLoopReport)
    assert report.is_healthy is True
    assert len(report.risks) == 0
    assert report.window_days == 7
    assert report.analyzed_at != ""


async def test_model_dominance_detected():
    """A model exceeding 70% usage triggers a dominance risk."""
    data = [{"model": "gpt-4o", "role": "generator"}] * 8 + [
        {"model": "claude-opus", "role": "generator"},
        {"model": "gemini-pro", "role": "generator"},
    ]
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    report = await detector.analyze()

    assert report.is_healthy is False
    dominance_risks = [r for r in report.risks if r.layer == "model_dominance"]
    assert len(dominance_risks) == 1
    assert dominance_risks[0].metric_value == 0.8
    assert dominance_risks[0].threshold == 0.70


async def test_eval_coupling_detected():
    """A model evaluating its own output above 40% triggers coupling risk."""
    data = [
        {"model": "gpt-4o", "role": "generator"},
        {"model": "gpt-4o", "role": "evaluator"},
        {"model": "gpt-4o", "role": "evaluator"},
        {"model": "gpt-4o", "role": "evaluator"},
        {"model": "claude-opus", "role": "evaluator"},
    ]
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    report = await detector.analyze()

    coupling_risks = [r for r in report.risks if r.layer == "eval_coupling"]
    assert len(coupling_risks) == 1
    assert coupling_risks[0].metric_value == 0.75
    assert coupling_risks[0].threshold == 0.40


async def test_is_healthy_threshold():
    """is_healthy returns False when any risk severity exceeds 0.6."""
    # Dominant model at 90% -> severity 0.9 -> unhealthy
    data = [{"model": "gpt-4o", "role": "generator"}] * 9 + [
        {"model": "claude-opus", "role": "generator"},
    ]
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    assert await detector.is_healthy() is False


async def test_is_healthy_returns_true_when_clean():
    """is_healthy returns True for a balanced system."""
    data = [
        {"model": "gpt-4o", "role": "generator"},
        {"model": "claude-opus", "role": "evaluator"},
    ]
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    assert await detector.is_healthy() is True


async def test_record_usage():
    """record_usage appends data used in subsequent analysis."""
    detector = SimpleFeedbackLoopDetector()
    for _ in range(8):
        detector.record_usage("gpt-4o", "generator")
    detector.record_usage("claude-opus", "generator")
    detector.record_usage("gemini-pro", "generator")

    report = await detector.analyze()
    dominance_risks = [r for r in report.risks if r.layer == "model_dominance"]
    assert len(dominance_risks) == 1


async def test_empty_data_is_healthy():
    """No usage data means no risks and a healthy report."""
    detector = SimpleFeedbackLoopDetector()
    report = await detector.analyze()
    assert report.is_healthy is True
    assert len(report.risks) == 0


async def test_custom_window_days():
    """The window_days parameter is reflected in the report."""
    detector = SimpleFeedbackLoopDetector()
    report = await detector.analyze(window_days=30)
    assert report.window_days == 30


async def test_usage_fetcher_callable():
    """A usage_fetcher callable is awaited and its result used."""

    async def fetcher():
        return [{"model": "gpt-4o", "role": "generator"}] * 8 + [
            {"model": "claude-opus", "role": "generator"},
            {"model": "gemini-pro", "role": "generator"},
        ]

    detector = SimpleFeedbackLoopDetector(usage_fetcher=fetcher)
    report = await detector.analyze()
    dominance_risks = [r for r in report.risks if r.layer == "model_dominance"]
    assert len(dominance_risks) == 1


async def test_reward_hacking_detected():
    """Quality up + diversity down triggers reward hacking risk."""
    data = [
        {"model": "a", "role": "generator", "quality": 0.5, "diversity": 0.8},
        {"model": "b", "role": "generator", "quality": 0.9, "diversity": 0.3},
    ]
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    report = await detector.analyze()
    hacking_risks = [r for r in report.risks if r.layer == "reward_hacking"]
    assert len(hacking_risks) == 1


async def test_concept_collapse_placeholder():
    """Concept collapse layer always passes (placeholder)."""
    data = [{"model": "a", "role": "generator"}] * 5
    detector = SimpleFeedbackLoopDetector(usage_data=data)
    report = await detector.analyze()
    collapse_risks = [r for r in report.risks if r.layer == "concept_collapse"]
    assert len(collapse_risks) == 0
