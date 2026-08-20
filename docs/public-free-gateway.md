# Public free LLM gateway (demo)

Expose Loom as a **keyless, brand-neutral, OpenAI-compatible** free model API.
Callers need nothing that ties them to Loom — no API key, no Loom account.

## Quick start

```bash
# Upstream free pool (example: OpenRouter free models)
export LOOM_LLM_BASE_URL=https://openrouter.ai/api/v1
export LOOM_LLM_API_KEY=sk-or-v1-YOUR_KEY          # server-side only
export LOOM_LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Optional allowlist (recommended for public)
export LOOM_FREE_MODELS=meta-llama/llama-3.3-70b-instruct:free,google/gemma-2-9b-it:free

# Rate limits for the public surface
export LOOM_PUBLIC_RPM=20
export LOOM_PUBLIC_MAX_TOKENS=2048

# Localhost (tunnel with cloudflared / ngrok) — or 0.0.0.0 behind Cloudflare
export LOOM_HOST=127.0.0.1
export LOOM_PORT=8080

python -m loom_ai.server_demo
```

`server_demo` forces `LOOM_DEMO_PUBLIC=1`, mounts `/v1`, strips secrets/knowledge/graph,
and allows non-loopback bind without `LOOM_API_KEY` (put a reverse proxy in front).

## Caller usage (no Loom key)

```bash
# List models
curl http://127.0.0.1:8080/v1/models

# Chat
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "meta-llama/llama-3.3-70b-instruct:free",
    "messages": [{"role":"user","content":"Hello"}]
  }'
```

OpenAI Python SDK:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="not-needed")
print(client.chat.completions.create(
    model="meta-llama/llama-3.3-70b-instruct:free",
    messages=[{"role":"user","content":"Hello"}],
).choices[0].message.content)
```

## Surfaces

| Path | Auth | Notes |
|------|------|--------|
| `GET /v1/models` | none | Free allowlist when set |
| `POST /v1/chat/completions` | none | Stream supported |
| `GET/POST /llm/*` | none | Loom-native shape (also kept) |
| `/health`, `/ready` | none | Probes only |
| secrets / knowledge / graph / … | **stripped** | |

## Upstream mix

Point `LOOM_LLM_BASE_URL` at any OpenAI-compatible free tier:

- OpenRouter `:free` models
- Groq free tier
- Google AI Studio (OpenAI-compat URL)
- Local Ollama

Multi-provider routing can use the adaptive router when configured; the public
`/v1` surface stays a single OpenAI-shaped endpoint.
