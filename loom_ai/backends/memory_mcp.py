"""In-memory MCP tool and resource providers for loom-ai.

Zero external dependencies.  Suitable for testing, local development,
and the 'crush' deployment profile.

Classes
-------
MemoryToolProvider      -- register async callables, dispatch by name
MemoryResourceProvider  -- register static resources, serve by URI
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

    Satisfies :class:`~loom_ai.protocols.ToolProvider` via structural
    subtyping.

    Usage::

        provider = MemoryToolProvider()
        provider.register(
            ToolDefinition(name="add", description="Add two numbers",
                           parameters={"a": {"type": "number"},
                                       "b": {"type": "number"}},
                           required_params=["a", "b"]),
            handler=my_add_handler,
        )
        result = await provider.call_tool("add", {"a": 1, "b": 2})
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

    async def call_tool(
        self, name: str, arguments: dict
    ) -> ToolResult:
        if name not in self._handlers:
            return ToolResult(
                tool_name=name,
                error=f"Tool not found: {name!r}",
            )

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


class MemoryResourceProvider:
    """In-memory resource registry serving static content by URI.

    Satisfies :class:`~loom_ai.protocols.ResourceProvider` via structural
    subtyping.

    Usage::

        provider = MemoryResourceProvider()
        provider.register(
            ResourceDefinition(uri="file:///readme", name="README",
                               description="Project readme"),
            content="# Hello",
        )
        result = await provider.read_resource("file:///readme")
    """

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
