"""Tests for Loom's MCP-shaped tool and resource contracts."""

import pytest

from loom_ai import (
    ResourceContent,
    ResourceDefinition,
    ResourceProvider,
    ToolDefinition,
    ToolProvider,
    ToolResult,
)
from loom_ai.backends.memory_mcp import MemoryResourceProvider, MemoryToolProvider


async def _add(a: int, b: int) -> int:
    return a + b


async def _fail(**kwargs: object) -> None:
    raise ValueError("something went wrong")


def _make_tool_provider() -> MemoryToolProvider:
    provider = MemoryToolProvider()
    provider.register(
        ToolDefinition(
            name="add",
            description="Add two numbers",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        ),
        handler=_add,
    )
    provider.register(
        ToolDefinition(
            name="boom",
            description="Always fails",
        ),
        handler=_fail,
    )
    return provider


def _make_resource_provider() -> MemoryResourceProvider:
    provider = MemoryResourceProvider()
    provider.register(
        ResourceDefinition(
            uri="file:///readme",
            name="README",
            description="Project readme",
            mime_type="text/markdown",
        ),
        content="# Hello World",
    )
    provider.register(
        ResourceDefinition(
            uri="file:///logo.png",
            name="Logo",
            description="Binary logo",
            mime_type="image/png",
        ),
        content=b"\x89PNG\r\n",
    )
    return provider


async def test_tool_provider_protocol_conformance():
    provider = MemoryToolProvider()
    assert isinstance(provider, ToolProvider)


async def test_list_tools():
    provider = _make_tool_provider()
    tools = await provider.list_tools()
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"add", "boom"}


async def test_call_tool_success():
    provider = _make_tool_provider()
    result = await provider.call_tool("add", {"a": 3, "b": 4})
    assert isinstance(result, ToolResult)
    assert result.tool_name == "add"
    assert result.output == 7
    assert result.error is None
    assert result.duration_ms is not None
    assert result.duration_ms >= 0


async def test_call_tool_missing_required_argument():
    provider = _make_tool_provider()
    result = await provider.call_tool("add", {"a": 3})
    assert result.error is not None
    assert "missing required" in result.error.lower()
    assert "b" in result.error


async def test_call_tool_unknown_argument():
    provider = _make_tool_provider()
    result = await provider.call_tool("add", {"a": 3, "b": 4, "c": 5})
    assert result.error is not None
    assert "unknown arguments" in result.error.lower()
    assert "c" in result.error


async def test_call_tool_invalid_schema():
    provider = MemoryToolProvider()
    provider.register(
        ToolDefinition(
            name="bad",
            description="Invalid schema",
            input_schema={"type": "object", "properties": []},
        ),
        handler=_add,
    )
    result = await provider.call_tool("bad", {})
    assert result.error is not None
    assert "properties" in result.error


async def test_call_tool_error():
    provider = _make_tool_provider()
    result = await provider.call_tool("boom", {})
    assert isinstance(result, ToolResult)
    assert result.tool_name == "boom"
    assert result.output is None
    assert result.error is not None
    assert "something went wrong" in result.error
    assert result.duration_ms is not None


async def test_call_tool_not_found():
    provider = _make_tool_provider()
    result = await provider.call_tool("nonexistent", {})
    assert isinstance(result, ToolResult)
    assert result.tool_name == "nonexistent"
    assert result.error is not None
    assert "not found" in result.error.lower()
    assert result.output is None


async def test_list_tools_empty():
    provider = MemoryToolProvider()
    tools = await provider.list_tools()
    assert tools == []


async def test_resource_provider_protocol_conformance():
    provider = MemoryResourceProvider()
    assert isinstance(provider, ResourceProvider)


async def test_list_resources():
    provider = _make_resource_provider()
    resources = await provider.list_resources()
    assert len(resources) == 2
    uris = {r.uri for r in resources}
    assert uris == {"file:///readme", "file:///logo.png"}


async def test_read_resource_text():
    provider = _make_resource_provider()
    result = await provider.read_resource("file:///readme")
    assert isinstance(result, ResourceContent)
    assert result.uri == "file:///readme"
    assert result.content == "# Hello World"
    assert result.mime_type == "text/markdown"


async def test_read_resource_binary():
    provider = _make_resource_provider()
    result = await provider.read_resource("file:///logo.png")
    assert isinstance(result, ResourceContent)
    assert result.uri == "file:///logo.png"
    assert isinstance(result.content, bytes)
    assert result.mime_type == "image/png"


async def test_read_resource_not_found():
    provider = _make_resource_provider()
    with pytest.raises(KeyError, match="not found"):
        await provider.read_resource("file:///missing")


async def test_list_resources_empty():
    provider = MemoryResourceProvider()
    resources = await provider.list_resources()
    assert resources == []


def test_loom_config_defaults_mcp_none():
    from loom_ai import LoomConfig

    cfg = LoomConfig.from_env()
    assert cfg.tools is None
    assert cfg.resources is None


def test_loom_config_mcp_memory(monkeypatch: pytest.MonkeyPatch):
    from loom_ai import LoomConfig

    monkeypatch.setenv("LOOM_TOOLS", "memory")
    monkeypatch.setenv("LOOM_RESOURCES", "memory")
    cfg = LoomConfig.from_env()
    assert isinstance(cfg.tools, ToolProvider)
    assert isinstance(cfg.resources, ResourceProvider)
