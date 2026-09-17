"""Tests for the model-backed Worker."""

from __future__ import annotations

from loom_ai.arbiter import Arbiter, ArbiterDecision, WorkerEvaluation
from loom_ai.fake_model_provider import FakeModelProvider
from loom_ai.intent import Intent
from loom_ai.model_worker import ModelWorker
from loom_ai.worker import WorkerContext, WorkerStatus


def test_model_worker_uses_provider_without_vendor_knowledge() -> None:
    worker = ModelWorker(FakeModelProvider(), model="test-model")
    context = WorkerContext(
        intent=Intent(
            goal="summarize the result",
            requirements=("be concise",),
            constraints=("do not expose credentials",),
        )
    )

    result = worker.execute(context)

    assert result.status is WorkerStatus.SUCCESS
    assert result.output.startswith("fake response: summarize the result")
    assert result.metadata["provider"] == "fake"
    assert result.metadata["model"] == "test-model"
    assert result.evidence[0]["type"] == "model-response"


def test_model_worker_composes_through_arbiter() -> None:
    worker = ModelWorker(FakeModelProvider(), model="test-model")
    intent = Intent(goal="exercise Stage 5")

    result = Arbiter(
        [worker],
        lambda worker_result, _context: WorkerEvaluation(
            ArbiterDecision.COMPLETE
            if worker_result.successful
            else ArbiterDecision.REPLAN
        ),
        max_retries=0,
    ).execute(WorkerContext(intent=intent))

    assert result.successful
    assert result.output[0].output == "fake response: exercise Stage 5"
