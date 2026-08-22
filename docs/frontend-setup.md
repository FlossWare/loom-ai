# Frontend Setup Guide

## Overview

loom-ai can serve as the AI backend for any coding assistant that supports
OpenAI-compatible APIs or MCP. All LLM calls are routed through
free-model routing to free API models — zero paid tokens.

Model routing is provided by [model-router-ai](https://github.com/FlossWare/model-router-ai),
which uses Thompson Sampling to dynamically select the best-performing free model
from providers like Cohere, Groq, Cerebras, and OpenRouter.

## Architecture

```
Frontend (Crush/OpenCode/Aider)
    ↓
loom-ai server (localhost:5000)
    ↓
model-router-ai (Thompson Sampling)
    ↓
Free APIs (Cohere, Groq, Cloudflare, Cerebras, HuggingFace, ...)
```

## Prerequisites

- **loom-ai installed**: `pip install flossware-loom-ai[server]`
- **loom-ai server running**:
  ```bash
  python -m loom_ai.server
  ```
- **Environment variables** (set before starting the server):
  - `LOOM_URL` — server URL (default: `http://127.0.0.1:5000`)
  - `LOOM_API_KEY` — optional bearer token for authentication
- **At least one free API key configured** (e.g., `PERSONAL_COHERE_API_KEY`)

## Crush Setup

```bash
# Generate JSON config
python -m loom_ai.clients.crush

# Or generate shell exports
python -m loom_ai.clients.crush --env
```

Environment variables:

```bash
export CRUSH_LLM_BASE_URL=http://localhost:5000/llm
export CRUSH_LLM_API_KEY=loom-ai
export CRUSH_CONSENSUS_URL=http://localhost:5000/consensus
```

Crush also supports MCP — add loom-ai as an MCP server for access to
`loom_resolve_issue` and other tools.

## OpenCode Setup

```bash
# Generate JSON config
python -m loom_ai.clients.opencode

# Write directly to ~/.config/opencode/config.json
python -m loom_ai.clients.opencode --write

# Or generate shell exports
python -m loom_ai.clients.opencode --env
```

Environment variables:

```bash
export OPENAI_BASE_URL=http://localhost:5000/llm
export OPENAI_API_KEY=loom-ai
export OPENCODE_MODEL=gpt-4o-mini
```

## Aider Setup

```bash
python -m loom_ai.clients.aider
```

Run Aider with:

```bash
aider --openai-api-base http://localhost:5000/llm --openai-api-key loom-ai
```

## Cursor Setup

```bash
python -m loom_ai.clients.cursor
```

Configure MCP server in Cursor settings to access loom-ai tools.

## Claude Code Setup

```bash
python -m loom_ai.clients.claude
```

Add to `claude_desktop_config.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "loom-ai": {
      "command": "python",
      "args": ["-m", "loom_ai.mcp_server"],
      "env": {
        "LOOM_URL": "http://127.0.0.1:5000"
      }
    }
  }
}
```

## Continue.dev Setup

```bash
python -m loom_ai.clients.continue_dev
```

Add the generated config to your Continue settings.

## OpenAI-Compatible Routes

The main server exposes both `/llm/chat` and `/v1/chat/completions`
(OpenAI-compatible). Tools that append `/v1/` work out of the box when
an LLM backend is configured.

## Token Savings

All frontends use free models via model-router-ai — approximately **99.5%
token savings** vs direct Claude/GPT usage. See
[token-savings.md](token-savings.md) for details.

## See Also

- [MCP Tool Reference](mcp-tools.md) — all 16 loom-ai MCP tools with parameters
- [Integrations](integrations.md) — compose with Trello, Notion, Slack via MCP
- [Client SDK](clients.md) — programmatic client SDK and CLI
- [Architecture](architecture.md) — overall loom-ai design
