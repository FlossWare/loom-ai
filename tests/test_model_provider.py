"""Conformance tests for the provider-neutral model contract."""

from __future__ import annotations

import pytest

from loom_ai import FakeModelProvider
from loom_ai.model import ModelProvider, ModelRequest, ModelResponse


def assert_provider_conforms(provider: ModelProvider) -> None:
    assert isinstance(provider.provider_id, str)
    assert provider.provider_id.strip()

    request = ModelRequest(prompt="hello Loom", model="test-model")
    response = provider.generate(request)

    assert isinstance(response.text, str)
    assert response.text.strip()
    assert response.provider == provider.provider_id
    assert response.provider.strip()
    assert response.model == request.model
    assert response.model.strip()
    assert response.finish_reason.strip()
    assert response.provenance["provider"] == provider.provider_id
    assert response.provenance["model"] == request.model

    serialized = " ".join(
        f"{key}={value}" for key, value in response.provenance.items()
    ).lower()
    for secret_marker in ("credential", "api_key", "secret", "password", "token"):
        assert secret_marker not in serialized


def test_fake_provider_conforms() -> None:
    assert_provider_conforms(FakeModelProvider())


def test_fake_provider_is_deterministic() -> None:
    provider = FakeModelProvider()
    request = ModelRequest(prompt="deterministic", model="test-model")

    first = provider.generate(request)
    second = provider.generate(request)

    assert first == second


def test_request_rejects_empty_or_whitespace_prompt_and_model() -> None:
    with pytest.raises(ValueError):
        ModelRequest(prompt=" ")
    with pytest.raises(ValueError):
        ModelRequest(prompt="hello", model=" \t")


def test_response_rejects_empty_required_fields() -> None:
    with pytest.raises(ValueError):
        ModelResponse(text=" ", provider="fake", model="test")
    with pytest.raises(ValueError):
        ModelResponse(text="result", provider=" ", model="test")
    with pytest.raises(ValueError):
        ModelResponse(text="result", provider="fake", model=" ")
    with pytest.raises(ValueError):
        ModelResponse(
            text="result", provider="fake", model="test", finish_reason=" "
        )


def test_request_mappings_are_immutable_copies() -> None:
    metadata = {"intent_id": "one"}
    request = ModelRequest(prompt="hello", metadata=metadata)
    metadata["intent_id"] = "two"

    assert request.metadata["intent_id"] == "one"
    with pytest.raises(TypeError):
        request.metadata["new"] = "value"  # type: ignore[index]


def test_response_mappings_are_immutable_copies() -> None:
    metadata = {"implementation": "test"}
    provenance = {"provider": "fake"}
    response = ModelResponse(
        text="result",
        provider="fake",
        model="test",
        metadata=metadata,
        provenance=provenance,
    )
    metadata["implementation"] = "changed"
    provenance["provider"] = "changed"

    assert response.metadata["implementation"] == "test"
    assert response.provenance["provider"] == "fake"
    with pytest.raises(TypeError):
        response.provenance["new"] = "value"  # type: ignore[index]
