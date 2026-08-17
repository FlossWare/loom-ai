"""Tests for loom_ai.backends.adversarial."""

import pytest

from loom_ai.backends.adversarial import (
    AdversarialVerifier,
    PanelMemberResult,
    VerificationResult,
    _model_family,
    _parse_verdict,
    aggregate_verdicts,
    select_panel,
)
from loom_ai.models import ChatMessage, ChatResponse

# ── Fake backend ───────────────────────────────────────────────────────


class FakeVerifierBackend:
    """Minimal LLMBackend that returns canned verification responses."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses: dict[str, str] = {}
        self.fail_models: set[str] = set()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append({"model": model, "temperature": temperature})
        if model in self.fail_models:
            raise RuntimeError(f"Model {model} unavailable")
        content = self.responses.get(
            model or "",
            "ANALYSIS: looks good\nERRORS: none\nVERDICT: CONFIRMED",
        )
        return ChatResponse(
            content=content,
            model=model or "default",
            provider="fake",
        )

    async def chat_stream(self, messages, **kwargs):
        yield "not used"

    async def list_models(self) -> list[str]:
        return list(self.responses.keys())


# ── _model_family tests ───────────────────────────────────────────────


class TestModelFamily:
    def test_slash_prefix(self):
        assert _model_family("openai/gpt-4o") == "openai"

    def test_dash_prefix(self):
        assert _model_family("gpt-4o") == "gpt"

    def test_no_separator(self):
        assert _model_family("llama") == "llama"

    def test_case_insensitive(self):
        assert _model_family("OpenAI/GPT-4o") == "openai"


# ── select_panel tests ────────────────────────────────────────────────


class TestSelectPanel:
    def test_excludes_candidate(self):
        panel = select_panel(
            ["m1", "m2", "m3", "m4"],
            "m2",
            panel_size=3,
        )
        assert "m2" not in panel
        assert len(panel) == 3

    def test_prefers_different_family(self):
        panel = select_panel(
            ["openai/gpt-4o", "openai/gpt-3.5", "anthropic/claude", "google/gemini"],
            "openai/gpt-4o",
            panel_size=2,
        )
        assert "openai/gpt-4o" not in panel
        # Should prefer anthropic and google over another openai.
        families = [_model_family(m) for m in panel]
        assert "openai" not in families

    def test_falls_back_to_same_family(self):
        panel = select_panel(
            ["openai/gpt-4o", "openai/gpt-3.5", "openai/gpt-4"],
            "openai/gpt-4o",
            panel_size=3,
        )
        # Only same-family models available (besides candidate).
        assert "openai/gpt-4o" not in panel
        assert len(panel) == 2  # Only 2 other openai models.

    def test_empty_models(self):
        panel = select_panel([], "m1", panel_size=3)
        assert panel == []

    def test_only_candidate_available(self):
        panel = select_panel(["m1"], "m1", panel_size=3)
        assert panel == []

    def test_panel_size_limit(self):
        panel = select_panel(
            ["m1", "m2", "m3", "m4", "m5"],
            "m1",
            panel_size=2,
        )
        assert len(panel) == 2


# ── _parse_verdict tests ──────────────────────────────────────────────


class TestParseVerdict:
    def test_confirmed(self):
        text = "ANALYSIS: ok\nERRORS: none\nVERDICT: CONFIRMED"
        assert _parse_verdict(text) == "CONFIRMED"

    def test_refuted(self):
        text = "ANALYSIS: bad\nERRORS: many\nVERDICT: REFUTED"
        assert _parse_verdict(text) == "REFUTED"

    def test_uncertain(self):
        text = "ANALYSIS: mixed\nERRORS: some\nVERDICT: UNCERTAIN"
        assert _parse_verdict(text) == "UNCERTAIN"

    def test_case_insensitive(self):
        text = "verdict: confirmed"
        assert _parse_verdict(text) == "CONFIRMED"

    def test_fallback_keyword_refuted(self):
        text = "The response is clearly REFUTED by evidence."
        assert _parse_verdict(text) == "REFUTED"

    def test_fallback_keyword_confirmed(self):
        text = "I believe this is CONFIRMED correct."
        assert _parse_verdict(text) == "CONFIRMED"

    def test_fallback_uncertain(self):
        text = "No clear verdict can be determined."
        assert _parse_verdict(text) == "UNCERTAIN"


# ── aggregate_verdicts tests ──────────────────────────────────────────


class TestAggregateVerdicts:
    def test_unanimous_confirmed(self):
        results = [
            PanelMemberResult(model="m1", verdict="CONFIRMED", raw_response=""),
            PanelMemberResult(model="m2", verdict="CONFIRMED", raw_response=""),
            PanelMemberResult(model="m3", verdict="CONFIRMED", raw_response=""),
        ]
        verdict, confidence = aggregate_verdicts(results)
        assert verdict == "CONFIRMED"
        assert confidence == pytest.approx(1.0)

    def test_unanimous_refuted(self):
        results = [
            PanelMemberResult(model="m1", verdict="REFUTED", raw_response=""),
            PanelMemberResult(model="m2", verdict="REFUTED", raw_response=""),
        ]
        verdict, confidence = aggregate_verdicts(results)
        assert verdict == "REFUTED"
        assert confidence == pytest.approx(1.0)

    def test_majority_confirmed(self):
        results = [
            PanelMemberResult(model="m1", verdict="CONFIRMED", raw_response=""),
            PanelMemberResult(model="m2", verdict="CONFIRMED", raw_response=""),
            PanelMemberResult(model="m3", verdict="REFUTED", raw_response=""),
        ]
        verdict, confidence = aggregate_verdicts(results)
        assert verdict == "CONFIRMED"
        assert confidence == pytest.approx(2 / 3)

    def test_no_majority_uncertain(self):
        results = [
            PanelMemberResult(model="m1", verdict="CONFIRMED", raw_response=""),
            PanelMemberResult(model="m2", verdict="REFUTED", raw_response=""),
            PanelMemberResult(model="m3", verdict="UNCERTAIN", raw_response=""),
        ]
        verdict, confidence = aggregate_verdicts(results)
        assert verdict == "UNCERTAIN"

    def test_empty_results(self):
        verdict, confidence = aggregate_verdicts([])
        assert verdict == "UNCERTAIN"
        assert confidence == 0.0

    def test_even_split(self):
        results = [
            PanelMemberResult(model="m1", verdict="CONFIRMED", raw_response=""),
            PanelMemberResult(model="m2", verdict="REFUTED", raw_response=""),
        ]
        verdict, confidence = aggregate_verdicts(results)
        # Neither achieves >50%, so UNCERTAIN.
        assert verdict == "UNCERTAIN"


# ── AdversarialVerifier integration tests ─────────────────────────────


class TestAdversarialVerifier:
    async def test_basic_verification(self):
        backend = FakeVerifierBackend()
        verifier = AdversarialVerifier(
            backend,
            ["m1", "m2", "m3", "m4"],
            panel_size=3,
        )
        result = await verifier.verify(
            "The sky is blue.",
            task="What color is the sky?",
            candidate_model="m1",
        )
        assert isinstance(result, VerificationResult)
        assert result.verdict == "CONFIRMED"
        assert result.candidate_model == "m1"
        assert "m1" not in result.panel_models
        assert len(result.panel_results) == 3

    async def test_mixed_verdicts(self):
        backend = FakeVerifierBackend()
        backend.responses = {
            "m2": "ANALYSIS: ok\nERRORS: none\nVERDICT: CONFIRMED",
            "m3": "ANALYSIS: bad\nERRORS: wrong\nVERDICT: REFUTED",
            "m4": "ANALYSIS: ok\nERRORS: none\nVERDICT: CONFIRMED",
        }
        verifier = AdversarialVerifier(
            backend,
            ["m1", "m2", "m3", "m4"],
            panel_size=3,
        )
        result = await verifier.verify(
            "2+2=4",
            task="What is 2+2?",
            candidate_model="m1",
        )
        assert result.verdict == "CONFIRMED"
        assert result.confidence == pytest.approx(2 / 3)

    async def test_all_refuted(self):
        backend = FakeVerifierBackend()
        backend.responses = {
            "m2": "VERDICT: REFUTED",
            "m3": "VERDICT: REFUTED",
            "m4": "VERDICT: REFUTED",
        }
        verifier = AdversarialVerifier(
            backend,
            ["m1", "m2", "m3", "m4"],
            panel_size=3,
        )
        result = await verifier.verify(
            "2+2=5",
            task="What is 2+2?",
            candidate_model="m1",
        )
        assert result.verdict == "REFUTED"
        assert result.confidence == pytest.approx(1.0)

    async def test_panel_member_failure(self):
        backend = FakeVerifierBackend()
        backend.fail_models = {"m3"}
        verifier = AdversarialVerifier(
            backend,
            ["m1", "m2", "m3", "m4"],
            panel_size=3,
        )
        result = await verifier.verify(
            "test",
            task="test task",
            candidate_model="m1",
        )
        # m3 fails -> UNCERTAIN; m2 and m4 -> CONFIRMED.
        # 2 CONFIRMED vs 1 UNCERTAIN -> majority CONFIRMED.
        assert result.verdict == "CONFIRMED"
        assert len(result.panel_results) == 3

    async def test_no_available_models(self):
        backend = FakeVerifierBackend()
        verifier = AdversarialVerifier(
            backend,
            ["m1"],  # Only the candidate model available.
            panel_size=3,
        )
        result = await verifier.verify(
            "test",
            task="test task",
            candidate_model="m1",
        )
        assert result.verdict == "UNCERTAIN"
        assert result.confidence == 0.0
        assert result.panel_models == []

    async def test_temperature_passed_to_backend(self):
        backend = FakeVerifierBackend()
        verifier = AdversarialVerifier(
            backend,
            ["m1", "m2", "m3"],
            panel_size=2,
            temperature=0.1,
        )
        await verifier.verify(
            "test",
            task="test",
            candidate_model="m1",
        )
        for call in backend.calls:
            assert call["temperature"] == 0.1

    async def test_candidate_model_excluded_from_panel(self):
        backend = FakeVerifierBackend()
        verifier = AdversarialVerifier(
            backend,
            ["m1", "m2", "m3"],
            panel_size=3,
        )
        result = await verifier.verify(
            "test",
            task="test",
            candidate_model="m1",
        )
        assert "m1" not in result.panel_models
