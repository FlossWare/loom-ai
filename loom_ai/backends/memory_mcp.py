"""In-memory implementations of Loom's MCP-shaped contracts.

These providers are intentionally transport-neutral.  They implement the
Loom ``ToolProvider`` and ``ResourceProvider`` contracts without depending
on an MCP SDK or providing an MCP server/transport themselves.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from loom_ai.models import (
    ResourceContent,
    ResourceDefinition,
    ToolDefinition,
    ToolResult,
)


class MemoryToolProvider:
    """In-memory tool registry that dispatches to async callables.

    Tool arguments are checked against the tool's JSON-Schema-shaped
    ``input_schema`` before the handler is invoked.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a tool with its definition and async handler."""
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    async def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        if name not in self._handlers:
            return ToolResult(
                tool_name=name,
                error=f"Tool not found: {name!r}",
            )

        definition = self._tools[name]
        validation_error = self._validate_arguments(definition, arguments)
        if validation_error is not None:
            return ToolResult(tool_name=name, error=validation_error)

        handler = self._handlers[name]
        start = time.monotonic()
        try:
            output = await handler(**arguments)
            elapsed = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_name=name,
                output=output,
                duration_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_name=name,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=elapsed,
            )

    @staticmethod
    def _validate_arguments(
        definition: ToolDefinition,
        arguments: dict,
    ) -> str | None:
        """Validate required and unknown top-level object properties."""
        schema = definition.input_schema or {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        if not isinstance(properties, dict):
            return (
                f"Invalid input schema for tool {definition.name!r}: "
                "properties must be an object"
            )
        if not isinstance(required, list):
            return (
                f"Invalid input schema for tool {definition.name!r}: "
                "required must be an array"
            )

        missing = [name for name in required if name not in arguments]
        if missing:
            return "Missing required arguments: " + ", ".join(sorted(missing))

        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            return "Unknown arguments: " + ", ".join(unknown)

        return None


class MemoryResourceProvider:
    """In-memory resource registry serving static content by URI."""

    def __init__(self) -> None:
        self._definitions: dict[str, ResourceDefinition] = {}
        self._contents: dict[str, str | bytes] = {}

    def register(
        self,
        definition: ResourceDefinition,
        content: str | bytes,
    ) -> None:
        """Register a resource with its definition and static content."""
        self._definitions[definition.uri] = definition
        self._contents[definition.uri] = content

    async def list_resources(self) -> list[ResourceDefinition]:
        return list(self._definitions.values())

    async def read_resource(self, uri: str) -> ResourceContent:
        if uri not in self._definitions:
            raise KeyError(f"Resource not found: {uri!r}")

        defn = self._definitions[uri]
        return ResourceContent(
            uri=uri,
            content=self._contents[uri],
            mime_type=defn.mime_type or "text/plain",
        )
