"""Tests for loom_ai.backends.structured_output.StructuredOutputBackend."""

from __future__ import annotations

import json

from loom_ai.backends.structured_output import (
    StructuredOutputBackend,
    _extract_json,
    _validate_schema,
)
from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.models_phase1 import StructuredResponse

# ── Mock LLMBackend ─────────────────────────────────────────────────────


class MockLLMBackend:
    """Minimal LLMBackend that returns configurable responses."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []
        self._call_index = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
            }
        )
        content = ""
        if self._call_index < len(self.responses):
            content = self.responses[self._call_index]
        self._call_index += 1
        return ChatResponse(content=content, model=model or "mock", provider="mock")

    async def chat_stream(self, messages, **kwargs):
        if False:
            yield "unused"

    async def list_models(self) -> list[str]:
        return ["mock-model"]


# ── Helper tests ────────────────────────────────────────────────────────


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"key": "value"}') == '{"key": "value"}'

    def test_json_with_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert _extract_json(text) == '{"key": "value"}'

    def test_json_with_bare_code_fence(self):
        text = '```\n{"key": "value"}\n```'
        assert _extract_json(text) == '{"key": "value"}'

    def test_json_with_whitespace(self):
        text = '  \n  {"key": "value"}  \n  '
        assert _extract_json(text) == '{"key": "value"}'


class TestValidateSchema:
    def test_valid_basic_schema(self):
        parsed = {"name": "Alice", "age": 30}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }
        is_valid, error = _validate_schema(parsed, schema)
        assert is_valid is True
        assert error == ""

    def test_missing_required_key(self):
        parsed = {"name": "Alice"}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }
        is_valid, error = _validate_schema(parsed, schema)
        assert is_valid is False
        assert "age" in error

    def test_no_required_keys(self):
        parsed = {"name": "Alice"}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        is_valid, error = _validate_schema(parsed, schema)
        assert is_valid is True

    def test_additional_properties_false(self):
        parsed = {"name": "Alice", "extra": "data"}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
        is_valid, error = _validate_schema(parsed, schema)
        assert is_valid is False
        assert "extra" in error


# ── Backend tests ───────────────────────────────────────────────────────


async def test_successful_json_parsing():
    """Backend correctly parses a valid JSON response."""
    data = {"answer": "42", "confidence": 0.95}
    backend = MockLLMBackend(responses=[json.dumps(data)])
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="What is the answer?")],
    )

    assert isinstance(result, StructuredResponse)
    assert result.parsed == data
    assert result.schema_valid is True
    assert result.retries_used == 0


async def test_json_in_code_fence():
    """Backend extracts JSON from Markdown code fences."""
    data = {"status": "ok"}
    backend = MockLLMBackend(
        responses=["```json\n" + json.dumps(data) + "\n```"],
    )
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Status?")],
    )

    assert result.parsed == data
    assert result.schema_valid is True
    assert result.retries_used == 0


async def test_retry_on_invalid_json():
    """Backend retries when the first response is not valid JSON."""
    valid_data = {"result": "success"}
    backend = MockLLMBackend(
        responses=[
            "This is not JSON at all",
            json.dumps(valid_data),
        ],
    )
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Give me JSON")],
        max_retries=3,
    )

    assert result.parsed == valid_data
    assert result.schema_valid is True
    assert result.retries_used == 1
    # Verify the fix prompt was appended
    second_call_msgs = backend.calls[1]["messages"]
    assert any("not valid JSON" in m.content for m in second_call_msgs)


async def test_exhausted_retries_on_invalid_json():
    """Backend returns schema_valid=False after exhausting retries."""
    backend = MockLLMBackend(
        responses=["not json", "still not json", "nope", "no way"],
    )
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Give me JSON")],
        max_retries=3,
    )

    assert result.parsed is None
    assert result.schema_valid is False
    assert result.retries_used == 3


async def test_schema_validation_success():
    """Backend validates parsed JSON against a schema."""
    data = {"name": "Alice", "age": 30}
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    backend = MockLLMBackend(responses=[json.dumps(data)])
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Generate a person")],
        schema=schema,
    )

    assert result.parsed == data
    assert result.schema_valid is True
    assert result.retries_used == 0


async def test_schema_validation_retry():
    """Backend retries when JSON is valid but does not match schema."""
    bad_data = {"name": "Alice"}  # missing required "age"
    good_data = {"name": "Alice", "age": 30}
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    backend = MockLLMBackend(
        responses=[json.dumps(bad_data), json.dumps(good_data)],
    )
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Generate a person")],
        schema=schema,
        max_retries=3,
    )

    assert result.parsed == good_data
    assert result.schema_valid is True
    assert result.retries_used == 1


async def test_schema_validation_exhausted():
    """Backend returns schema_valid=False when schema never matches."""
    bad_data = {"name": "Alice"}
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    backend = MockLLMBackend(
        responses=[json.dumps(bad_data)] * 4,
    )
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Generate a person")],
        schema=schema,
        max_retries=3,
    )

    assert result.parsed == bad_data
    assert result.schema_valid is False
    assert result.retries_used == 3


async def test_response_format_json_adds_system_message():
    """Setting response_format='json' prepends a JSON system message."""
    data = {"answer": "yes"}
    backend = MockLLMBackend(responses=[json.dumps(data)])
    structured = StructuredOutputBackend(backend)

    await structured.chat_structured(
        [ChatMessage(role="user", content="Is the sky blue?")],
        response_format="json",
    )

    first_call_msgs = backend.calls[0]["messages"]
    assert first_call_msgs[0].role == "system"
    assert "valid JSON" in first_call_msgs[0].content


async def test_response_format_text_no_system_message():
    """Default response_format='text' does not inject a system message."""
    data = {"answer": "yes"}
    backend = MockLLMBackend(responses=[json.dumps(data)])
    structured = StructuredOutputBackend(backend)

    await structured.chat_structured(
        [ChatMessage(role="user", content="Is the sky blue?")],
        response_format="text",
    )

    first_call_msgs = backend.calls[0]["messages"]
    # Only the user message, no injected system message
    assert len(first_call_msgs) == 1
    assert first_call_msgs[0].role == "user"


async def test_model_passthrough():
    """Model kwarg is forwarded to the underlying backend."""
    data = {"status": "ok"}
    backend = MockLLMBackend(responses=[json.dumps(data)])
    structured = StructuredOutputBackend(backend)

    await structured.chat_structured(
        [ChatMessage(role="user", content="Check")],
        model="special-model",
    )

    assert backend.calls[0]["model"] == "special-model"


async def test_default_model():
    """StructuredOutputBackend passes its default_model to the backend."""
    data = {"status": "ok"}
    backend = MockLLMBackend(responses=[json.dumps(data)])
    structured = StructuredOutputBackend(backend, default_model="my-default")

    await structured.chat_structured(
        [ChatMessage(role="user", content="Check")],
    )

    assert backend.calls[0]["model"] == "my-default"


async def test_raw_text_preserved():
    """The raw_text field always contains the last raw response."""
    raw = '{"result": "hello"}'
    backend = MockLLMBackend(responses=[raw])
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Say hello")],
    )

    assert result.raw_text == raw
    assert result.content == raw


async def test_no_retries():
    """With max_retries=0, no retries are attempted on failure."""
    backend = MockLLMBackend(responses=["not json"])
    structured = StructuredOutputBackend(backend)

    result = await structured.chat_structured(
        [ChatMessage(role="user", content="Give JSON")],
        max_retries=0,
    )

    assert result.parsed is None
    assert result.schema_valid is False
    assert result.retries_used == 0
    assert len(backend.calls) == 1


async def test_satisfies_protocol():
    """StructuredOutputBackend satisfies StructuredOutputMixin protocol."""
    from loom_ai.contracts_phase1 import StructuredOutputMixin

    backend = MockLLMBackend()
    structured = StructuredOutputBackend(backend)
    assert isinstance(structured, StructuredOutputMixin)
