# MCP Tool Reference

## Overview
loom-ai exposes tools via MCP (Model Context Protocol) over stdio JSON-RPC. Any MCP-compatible client can connect to utilize these tools.

## Connection
To start the MCP server, run the following command:
```
python -m loom_ai.mcp_server
```

**Configuration Example for `claude_desktop_config.json`:**
```json
{"command": "python", "args": ["-m", "loom_ai.mcp_server"]}
```

**Environment Variables:**
- `LOOM_URL`: URL of the Loom AI server (default: `http://127.0.0.1:5000`)
- `LOOM_API_KEY`: Optional API key for authentication

## Tool Reference

| Tool Name            | Description                                      | Required Params       | Optional Params               |
|----------------------|--------------------------------------------------|-----------------------|-------------------------------|
| `loom_chat`          | Send chat completion                            | `messages`            | `model`, `temperature`, `max_tokens` |
| `loom_list_models`   | List available models                           | -                     | -                             |
| `loom_search`        | Full-text search knowledge base                 | `query`               | `limit`                       |
| `loom_store`         | Store document                                  | `title`, `content`    | `category`                    |
| `loom_consensus`     | Multi-model consensus                           | `prompt`, `models`    | -                             |
| `loom_synthesize`    | Multi-model synthesis with arbiter              | `prompt`, `models`    | `arbiter_model`               |
| `loom_queue_enqueue` | Add to queue                                    | `queue_name`, `payload` | -                             |
| `loom_queue_status`  | Queue status                                    | `queue_name`          | -                             |
| `loom_secret_list`   | List secret names                               | -                     | -                             |
| `loom_secret_get`    | Get secret                                      | `name`, `reason`      | -                             |
| `loom_graph_add_node`| Add graph node                                  | `label`               | `properties`                  |
| `loom_graph_neighbors` | Get neighbors                                  | `node_id`             | `edge_label`                  |
| `loom_router_select` | Select model via Thompson Sampling              | `task_type`           | -                             |
| `loom_router_stats`  | Router stats                                    | -                     | -                             |
| `loom_health`        | Health check                                    | -                     | -                             |
| `loom_resolve_issue` | Resolve GitHub issue end-to-end                 | `issue_number`        | `workspace`, `issue_text`     |

## loom_resolve_issue Detailed

**How it Works:**
1. **Fetch Issue**: Retrieves the specified GitHub issue.
2. **Gather Context**: Collects relevant context from the issue and repository.
3. **Plan**: Generates a plan using a free model via `FreeModelRouter`.
4. **Implement**: Executes the plan, implementing the necessary changes.
5. **Review Loop**: Multi-model review of the implementation.
6. **Lint & Test**: Runs linting and testing on the changes.
7. **Commit & PR**: Commits the changes and creates a pull request.

**Key Features:**
- All LLM work is performed by free models (e.g., Cohere, Groq) via `FreeModelRouter`.
- **Zero paid tokens consumed**.
- Returns the PR URL on success.

**Return Values:**
- `success`: Boolean indicating success.
- `error`: Error message if failed.
- `plan`: Generated plan.
- `pr_url`: URL of the created pull request.

## Protocol Versions Supported
- `2024-11-05`
- `2025-03-26`

## See Also

- [Frontend Setup](frontend-setup.md) — connect Crush, OpenCode, Aider, Cursor, Claude Code
- [Integrations](integrations.md) — compose loom-ai with Trello, Notion, Slack via MCP
- [Token Savings](token-savings.md) — how FreeModelRouter saves ~99.5% of paid tokens
- [Architecture](architecture.md) — overall loom-ai design and contract layer
