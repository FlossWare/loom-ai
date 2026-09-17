"""Conformance tests for the provider-neutral model contract."""

from __future__ import annotations

from loom_ai.fake_model_provider import FakeModelProvider
from loom_ai.model import ModelProvider, ModelRequest


def assert_provider_conforms(provider: ModelProvider) -> None:
    request = ModelRequest(prompt="hello Loom", model="test-model")
    response = provider.generate(request)

    assert isinstance(response.text, str)
    assert response.text
    assert response.provider == provider.provider_id
    assert response.model == request.model
    assert response.finish_reason
    assert response.provenance["provider"] == provider.provider_id
    assert response.provenance["model"] == request.model
    assert "credential" not in response.provenance
    assert "api_key" not in response.provenance
    assert "secret" not in response.provenance


def test_fake_provider_conforms() -> None:
    assert_provider_conforms(FakeModelProvider())


def test_fake_provider_is_deterministic() -> None:
    provider = FakeModelProvider()
    request = ModelRequest(prompt="deterministic", model="test-model")

    first = provider.generate(request)
    second = provider.generate(request)

    assert first == second


def test_request_rejects_empty_prompt() -> None:
    try:
        ModelRequest(prompt="")
    except ValueError as exc:
        assert str(exc) == "ModelRequest prompt must not be empty"
    else:
        raise AssertionError("expected empty prompt to be rejected")
