# MCP Integrations Guide

## Overview

loom-ai uses MCP (Model Context Protocol) for tool interoperability. Any
MCP-compatible service can be composed alongside loom-ai in a frontend that
supports multiple MCP servers. This allows flexible composition of AI
capabilities with project management, documentation, and communication tools.

## Architecture

The frontend (Crush, OpenCode, Claude Code, Cursor) acts as the MCP host,
connecting to multiple MCP servers simultaneously:

```
Frontend (MCP Host)
  ├── loom-ai MCP     → AI brain (free model routing, consensus, issue resolution)
  ├── Trello MCP      → boards, cards, checklists
  ├── Notion MCP      → pages, databases, blocks
  ├── Slack MCP       → messages, channels
  ├── GitHub MCP      → issues, PRs, code search
  └── Google Drive    → docs, sheets, slides
```

loom-ai focuses on being the AI backend; the frontend orchestrates across
all connected MCP servers.

## Community MCP Servers

| Integration   | What it does                              | Notes                              |
|---------------|-------------------------------------------|------------------------------------|
| **Trello**    | Read/write boards, cards, lists           | Community MCP server available     |
| **Notion**    | Read/write pages, databases, blocks       | Community MCP server available     |
| **Google Drive** | Read/write docs, sheets, slides        | Various community implementations |
| **Slack**     | Send/read messages, manage channels       | Community MCP server available     |
| **Linear**    | Issue tracking, project management        | Community MCP server available     |
| **Jira**      | Enterprise issue tracking                 | Community MCP server available     |
| **GitHub**    | Issues, PRs, code search                  | Built into many frontends; also available as standalone MCP server |

Check [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
for the latest directory of community MCP servers.

## Example Workflow

**Scenario**: "Create a Trello card for bug #123, then resolve it."

1. Frontend calls **Trello MCP** → creates card for bug #123
2. Frontend calls **loom-ai MCP** (`loom_resolve_issue`) → plans, implements,
   reviews with free models, creates PR
3. Frontend calls **Trello MCP** → moves card to "In Review"
4. Frontend calls **Slack MCP** → notifies team channel with PR link

All LLM work in step 2 is done by free models via model-router-ai — zero
paid tokens.

## Configuration

To configure multiple MCP servers, add them to your frontend's MCP
configuration. Example for `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "loom-ai": {
      "command": "python",
      "args": ["-m", "loom_ai.mcp_server"],
      "env": {
        "LOOM_URL": "http://127.0.0.1:5000"
      }
    },
    "trello": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-trello"],
      "env": {
        "TRELLO_API_KEY": "your-trello-api-key"
      }
    },
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "your-slack-bot-token"
      }
    }
  }
}
```

Each MCP server runs as a separate stdio process. The frontend manages
connections to all of them and routes tool calls based on the tool name
prefix.

## Future

loom-ai could add native adapters for popular integrations, but MCP
composability means the frontend handles orchestration. This lets loom-ai
focus on being the best free AI backend while leveraging the growing
ecosystem of MCP-compatible tools.

## See Also

- [MCP Tool Reference](mcp-tools.md) — all 16 loom-ai MCP tools with parameters
- [Frontend Setup](frontend-setup.md) — connect Crush, OpenCode, Aider, Cursor, Claude Code
- [Token Savings](token-savings.md) — cost analysis and model-router-ai savings
