"""Structured-output backend wrapping any LLMBackend.

Adds schema-validated JSON output with automatic retries to any
existing ``LLMBackend`` implementation.  Satisfies the
:class:`~loom_ai.contracts_phase1.StructuredOutputMixin` protocol via
structural subtyping.

Optional dependency: ``jsonschema`` is used for full JSON Schema
validation when available; otherwise a basic dict-key check is used.

Zero required external dependencies beyond the standard library.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.models_phase1 import StructuredResponse

if TYPE_CHECKING:
    from loom_ai.protocols import LLMBackend

# ── optional jsonschema import ──────────────────────────────────────────

try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]
    _HAS_JSONSCHEMA = False


# ── helpers ─────────────────────────────────────────────────────────────


def _extract_json(text: str) -> str:
    """Extract a JSON object or array from *text*.

    Handles the common case where models wrap JSON in a Markdown
    code fence (````json ... ````).  Falls back to returning *text*
    unchanged so ``json.loads`` can attempt parsing directly.
    """
    stripped = text.strip()

    # Strip markdown code fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    return stripped


def _validate_schema(parsed: dict, schema: dict) -> tuple[bool, str]:
    """Validate *parsed* against *schema*.

    Returns ``(is_valid, error_message)``.  Uses ``jsonschema`` when
    available; otherwise checks that all ``required`` keys are present
    and all ``properties`` keys are a subset of the parsed dict.
    """
    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=parsed, schema=schema)
            return True, ""
        except jsonschema.ValidationError as exc:
            return False, str(exc.message)

    # Fallback: basic key checking
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    missing = [k for k in required if k not in parsed]
    if missing:
        return False, f"Missing required keys: {missing}"

    if properties:
        extra = [k for k in parsed if k not in properties]
        if extra and schema.get("additionalProperties") is False:
            return False, f"Unexpected keys: {extra}"

    return True, ""


class StructuredOutputBackend:
    """Wraps any ``LLMBackend`` to add structured-output support.

    Satisfies :class:`~loom_ai.contracts_phase1.StructuredOutputMixin`
    via structural subtyping -- no inheritance required.

    Parameters
    ----------
    backend:
        Any object satisfying the ``LLMBackend`` protocol.
    default_model:
        Model id passed to the underlying backend when callers do not
        specify one via ``**kwargs``.
    """

    def __init__(
        self,
        backend: LLMBackend,
        *,
        default_model: str | None = None,
    ) -> None:
        self._backend = backend
        self._default_model = default_model

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict | None = None,
        tools: list[dict] | None = None,
        response_format: str = "text",
        max_retries: int = 3,
        **kwargs: Any,
    ) -> StructuredResponse:
        """Send a chat completion request with structured output constraints.

        When *response_format* is ``"json"``, a system message is
        prepended instructing the model to respond with valid JSON.

        If *schema* is provided, each response is validated against it
        and retries are attempted (up to *max_retries*) with a fix
        prompt appended to the conversation.
        """
        working_messages = list(messages)

        # Prepend a JSON instruction when response_format="json"
        if response_format == "json":
            json_instruction = ChatMessage(
                role="system",
                content=(
                    "You must respond with valid JSON only. "
                    "Do not include any text outside the JSON object."
                ),
            )
            working_messages = [json_instruction, *working_messages]

        model = kwargs.pop("model", self._default_model)
        temperature = kwargs.pop("temperature", 0.7)

        raw_text = ""
        retries_used = 0

        for attempt in range(1 + max_retries):
            response: ChatResponse = await self._backend.chat(
                working_messages,
                model=model,
                temperature=temperature,
            )
            raw_text = response.content

            # Try to parse as JSON
            try:
                extracted = _extract_json(raw_text)
                parsed = json.loads(extracted)
            except (json.JSONDecodeError, ValueError):
                if attempt < max_retries:
                    retries_used += 1
                    working_messages.append(
                        ChatMessage(role="assistant", content=raw_text),
                    )
                    working_messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                "Your previous response was not valid JSON. "
                                "Please respond with valid JSON only."
                            ),
                        ),
                    )
                    continue

                # Exhausted retries -- return what we have
                return StructuredResponse(
                    content=raw_text,
                    parsed=None,
                    schema_valid=False,
                    raw_text=raw_text,
                    retries_used=retries_used,
                )

            # If no schema, parsed JSON is good enough
            if schema is None:
                return StructuredResponse(
                    content=raw_text,
                    parsed=parsed if isinstance(parsed, dict) else {"_value": parsed},
                    schema_valid=True,
                    raw_text=raw_text,
                    retries_used=retries_used,
                )

            # Validate against schema
            is_valid, error_msg = _validate_schema(
                parsed if isinstance(parsed, dict) else {},
                schema,
            )

            if is_valid:
                return StructuredResponse(
                    content=raw_text,
                    parsed=parsed if isinstance(parsed, dict) else {"_value": parsed},
                    schema_valid=True,
                    raw_text=raw_text,
                    retries_used=retries_used,
                )

            # Schema validation failed -- retry with a fix prompt
            if attempt < max_retries:
                retries_used += 1
                working_messages.append(
                    ChatMessage(role="assistant", content=raw_text),
                )
                working_messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            "Your JSON response did not match the "
                            f"required schema. Error: {error_msg}. "
                            "Please fix and respond with valid JSON "
                            "matching the schema."
                        ),
                    ),
                )
                continue

            # Exhausted retries with schema failure
            return StructuredResponse(
                content=raw_text,
                parsed=parsed if isinstance(parsed, dict) else {"_value": parsed},
                schema_valid=False,
                raw_text=raw_text,
                retries_used=retries_used,
            )

        # Should not reach here, but satisfy the type checker
        return StructuredResponse(  # pragma: no cover
            content=raw_text,
            parsed=None,
            schema_valid=False,
            raw_text=raw_text,
            retries_used=retries_used,
        )
