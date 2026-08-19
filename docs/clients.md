# Client SDK

loom-ai ships a dual-mode async client SDK so the same application code can
run against **embedded backends** or a **remote REST server**.

## Auto-detection

```python
from loom_ai.clients import get_client

client = await get_client()
# LocalClient  when LOOM_URL and LOOM_HOST are unset
# LoomClient   when LOOM_URL or LOOM_HOST is set
```

| Mode | Trigger | Transport |
|------|---------|-----------|
| Local (`LocalClient`) | neither `LOOM_URL` nor `LOOM_HOST` set | In-process backends via `LoomConfig.from_env()` |
| Remote (`LoomClient`) | `LOOM_URL` or `LOOM_HOST` set | HTTP to the loom-ai FastAPI server |

## Capability matrix

| Capability | LocalClient | LoomClient (REST) |
|------------|:-----------:|:-----------------:|
| Health / ready | yes | yes |
| LLM chat + stream | yes | yes |
| List models | yes | yes |
| Consensus gather / synthesize | yes | yes |
| Knowledge stats / list / store | yes | yes |
| Text / semantic / hybrid search | yes | yes |
| Secrets list / get | yes (audit-logged) | yes (server audit on reveal) |
| Queue status / enqueue | yes | yes |
| Graph nodes / edges / neighbors | yes | yes |
| Tools list / call | yes | yes |
| Resources list / read | yes | yes |
| Full server-only routes (e.g. secrets reveal with reason header) | n/a | yes |

Both clients return plain `dict` payloads for transport neutrality. Library
callers that prefer typed models can construct them from `loom_ai.models`.

## CLI

```bash
pip install flossware-loom-ai[cli]
loom health
loom chat "Hello" --stream
loom consensus "prompt" --models gemini,gpt-4o
```

The CLI uses `get_client()` and therefore inherits local/remote auto-detection.

## Tool adapters

Adapters under `loom_ai.clients.*` emit config or env vars for Crush, OpenCode,
Aider, Cursor, Continue.dev, and Claude Code (MCP bridge).

**Known limitation:** adapters that generate OpenAI-compatible base URLs point
at `/llm`. The loom-ai server exposes `/llm/chat` and `/llm/models`, not
`/v1/chat/completions`. Tools that always append `/v1/chat/completions` need a
proxy or custom base-path support until an OpenAI-compatible route is added.

Set `LOOM_URL` (and optionally `LOOM_API_KEY`) before generating adapter config.


## Secrets and audit

`LocalClient.get_secret(name, reason=...)` accepts ``reason`` for API parity
with the REST reveal flow. In **local** mode the reason is only logged in-process;
it is not a durable remote audit record. Server-side
``POST /secrets/{name}/reveal`` requires ``X-Secret-Access-Reason`` and is
audit-logged by the server.
