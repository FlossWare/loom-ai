"""Conformance tests for ToolProvider implementations.

Any backend that satisfies the ToolProvider protocol should pass all
tests in this module.  Override the ``tool_provider`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

from loom_ai.models import ToolDefinition, ToolResult

# -- list_tools() ----------------------------------------------------------


async def test_list_tools_returns_list(tool_provider):
    """list_tools() returns a list of ToolDefinition instances."""
    tools = await tool_provider.list_tools()

    assert isinstance(tools, list)
    assert len(tools) >= 1
    assert all(isinstance(t, ToolDefinition) for t in tools)


async def test_tool_definition_has_name_and_description(tool_provider):
    """Each ToolDefinition has a non-empty name and description."""
    tools = await tool_provider.list_tools()

    for tool in tools:
        assert isinstance(tool.name, str)
        assert len(tool.name) > 0
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


async def test_tool_definition_has_input_schema(tool_provider):
    """Each ToolDefinition has an input_schema dict."""
    tools = await tool_provider.list_tools()

    for tool in tools:
        assert isinstance(tool.input_schema, dict)
        assert tool.input_schema.get("type") == "object"


# -- call_tool() -----------------------------------------------------------


async def test_call_tool_returns_tool_result(tool_provider):
    """call_tool() returns a ToolResult instance."""
    result = await tool_provider.call_tool("echo", {"message": "hi"})

    assert isinstance(result, ToolResult)
    assert result.tool_name == "echo"
    assert result.error is None
    assert result.output is not None


async def test_call_tool_unknown_returns_error(tool_provider):
    """Calling an unknown tool returns a ToolResult with an error."""
    result = await tool_provider.call_tool("nonexistent", {})

    assert isinstance(result, ToolResult)
    assert result.error is not None
    assert len(result.error) > 0
