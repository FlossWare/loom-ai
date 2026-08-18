"""Claude Code adapter for loom-ai.

Configures Claude Code to use loom-ai as a proxy / knowledge backend.
Claude Code can connect to loom-ai's REST API for:
- Knowledge search (via MCP tool integration)
- Document storage (via MCP resource integration)
- Consensus queries (via custom tool calls)

Usage::

    # Generate Claude Code MCP server config for loom-ai
    python -m loom_ai.clients.claude

    # Generate environment variables
    python -m loom_ai.clients.claude --env

Integration approaches:
    1. MCP Server — loom-ai exposes /tools and /resources endpoints that
       follow MCP conventions.  Add loom-ai as an MCP server in
       claude_desktop_config.json or .claude/settings.json.

    2. Custom API — use LoomClient directly in Claude Code hooks or
       custom commands to query consensus, search knowledge, or store
       documents.

    3. Proxy mode — point Claude Code at loom-ai's /llm endpoint as an
       OpenAI-compatible proxy for model routing and consensus.
"""

from __future__ import annotations

import json
import os
import shlex
import sys


def generate_mcp_config(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
) -> dict:
    """Generate Claude Code MCP server configuration for loom-ai.

    Add this to ``~/.claude/claude_desktop_config.json`` under
    ``mcpServers`` or to ``.claude/settings.json``.
    """
    return {
        "mcpServers": {
            "loom-ai": {
                "command": "python",
                "args": ["-m", "loom_ai.clients.claude.mcp_bridge"],
                "env": {
                    "LOOM_URL": loom_url,
                    "LOOM_API_KEY": api_key,
                },
            },
        },
    }


def generate_env(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
) -> str:
    """Generate shell exports for Claude Code integration."""
    lines = [
        f"export LOOM_URL={shlex.quote(loom_url)}",
        f"export LOOM_API_KEY={shlex.quote(api_key)}",
        "",
        "# Add to CLAUDE.md for Claude Code awareness:",
        "# When querying the knowledge base, use the loom-ai MCP server.",
        "# Tools: loom_search, loom_store, loom_consensus",
    ]
    return "\n".join(lines)


def generate_claude_md_snippet() -> str:
    """Generate a CLAUDE.md snippet for loom-ai integration."""
    return """## Loom-AI Integration

This project uses loom-ai for LLM orchestration:
- **Search knowledge**: Use the `loom_search` MCP tool to query the knowledge base
- **Store documents**: Use the `loom_store` MCP tool to persist documents
- **Consensus**: Use the `loom_consensus` MCP tool for multi-model consensus
- **Server**: loom-ai runs at $LOOM_URL (default http://127.0.0.1:5000)
"""


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")

    if "--env" in sys.argv:
        print(generate_env(loom_url, api_key))
    elif "--claude-md" in sys.argv:
        print(generate_claude_md_snippet())
    else:
        config = generate_mcp_config(loom_url, api_key)
        print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
