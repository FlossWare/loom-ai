"""Regression tests for explicit consensus failure reporting."""

from loom_ai.consensus import ConsensusEngine
from loom_ai.models import ChatMessage, ChatResponse


class ArbiterFailureBackend:
    """Backend that succeeds for workers and fails for the arbiter."""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if model == "arbiter":
            raise RuntimeError("arbiter unavailable")
        return ChatResponse(content=f"response from {model}", model=model or "default")

    async def chat_stream(self, messages, **kwargs):
        if False:
            yield "unused"

    async def list_models(self) -> list[str]:
        return ["worker"]


async def test_arbiter_failure_is_explicit():
    engine = ConsensusEngine(ArbiterFailureBackend(), retries=0)

    result = await engine.synthesize(
        "test",
        ["worker"],
        arbiter_model="arbiter",
    )

    assert result.arbiter_attempted is True
    assert result.arbiter_error == "RuntimeError: Arbiter call failed after retries"
    assert len(result.worker_responses) == 1
    assert result.synthesis.content.startswith("Arbiter synthesis failed")


def test_consensus_result_defaults_to_not_attempted():
    from loom_ai.consensus import ConsensusResult

    result = ConsensusResult(synthesis=ChatResponse(content="test"))
    assert result.arbiter_attempted is False
    assert result.arbiter_error is None
