# loom-ai

Pluggable AI orchestration framework with swappable backends. Zero required dependencies.

## Install

```bash
pip install loom-ai              # core (stdlib only)
pip install loom-ai[server]      # + FastAPI REST server
pip install loom-ai[postgresql]  # + PostgreSQL/pgvector storage
pip install loom-ai[redis]       # + Redis queues
pip install loom-ai[all]         # everything
```

## Quick Start

### As a Python library

```python
from loom_ai import LoomConfig, Document, ChatMessage

# Zero-config: all in-memory / no-op backends
cfg = LoomConfig.from_env()

# Store a document
doc_id = await cfg.storage.store_document(Document(
    id="doc-1", title="Example", content="Hello world"
))

# Multi-model consensus (requires LOOM_LLM_BASE_URL)
responses = await cfg.llm.consensus(
    [ChatMessage(role="user", content="Explain distributed systems")],
    models=["gemini-3.5-flash", "llama-3.3-70b", "mistral-small"],
)
```

### As a REST server

```bash
# Minimal — just LLM routing
export LOOM_LLM_BASE_URL=http://localhost:4000/v1
python -m loom_ai

# Full stack
export LOOM_STORAGE=postgresql
export LOOM_QUEUE=redis
export LOOM_GRAPH=memory
export LOOM_LLM_BASE_URL=http://localhost:4000/v1
python -m loom_ai
```

Routes mount dynamically based on configuration:

| Backend | Routes | When |
|---------|--------|------|
| Storage | `/knowledge/*` | Always |
| Queue | `/pipeline/*` | Always |
| Search | `/search/*` | Always |
| Secrets | `/secrets/*` | Always |
| LLM | `/llm/*` | `LOOM_LLM_BASE_URL` set |
| Graph | `/graph/*` | `LOOM_GRAPH != disabled` |
| Health | `/health` | Always |

## Configuration

All via environment variables (defaults in parentheses):

| Variable | Options | Default |
|----------|---------|---------|
| `LOOM_STORAGE` | `memory`, `postgresql` | `memory` |
| `LOOM_QUEUE` | `memory`, `redis` | `memory` |
| `LOOM_SECRETS` | `env`, `dotenv`, `postgresql` | `env` |
| `LOOM_EMBEDDING` | `noop`, `openai`, `litellm` | `noop` |
| `LOOM_SEARCH` | `memory`, `postgresql` | `memory` |
| `LOOM_GRAPH` | `disabled`, `memory`, `orientdb` | `disabled` |
| `LOOM_LLM_BASE_URL` | Any OpenAI-compatible URL | *(none)* |
| `LOOM_LLM_API_KEY` | Bearer token | *(none)* |
| `LOOM_LLM_MODEL` | Default model id | `gpt-4o-mini` |
| `LOOM_HOST` | Server bind address | `0.0.0.0` |
| `LOOM_PORT` | Server port | `5000` |

Don't set it? Don't get it. Set nothing at all and you get a pure in-memory orchestrator.

## Architecture

```
loom_ai/
  protocols.py          7 Protocol interfaces (async, stdlib-only)
  models.py             9 dataclasses (Document, Chunk, ChatMessage, etc.)
  config.py             LoomConfig registry with from_env() factory
  prompts.py            Built-in consensus prompt templates
  server.py             Optional FastAPI REST server
  backends/
    memory.py           In-memory implementations (zero deps)
    env_secrets.py      Environment variable secrets
    http_llm.py         HTTP LLM backend (urllib, zero deps)
```

## 7 Pluggable Protocols

| Protocol | Purpose | Default | Enterprise |
|----------|---------|---------|------------|
| `StorageBackend` | Documents, chunks, embeddings | In-memory dicts | PostgreSQL + pgvector |
| `QueueBackend` | Named task queues | In-memory deque | Redis |
| `SecretsBackend` | API keys and config | `os.environ` | PostgreSQL encrypted |
| `EmbeddingBackend` | Text to vectors | Zero vectors | OpenAI / Jina / Voyage |
| `SearchBackend` | Full-text + semantic | Substring + cosine | tsvector + pgvector ANN |
| `GraphBackend` | Knowledge graph | Disabled | OrientDB |
| `LLMBackend` | Chat + consensus | HTTP (any OpenAI-compatible) | Same |

## Multi-Model Consensus

Fan out to N models, synthesize with an arbiter:

```python
from loom_ai.prompts import build_worker_messages, build_arbiter_messages

# Workers respond independently
worker_msgs = build_worker_messages("review", "Check this code for bugs")
responses = await cfg.llm.consensus(
    [ChatMessage(role=m["role"], content=m["content"]) for m in worker_msgs],
    models=["gemini-3.5-flash", "llama-3.3-70b", "codestral"],
    timeout_seconds=60,
    retries=2,
)

# Arbiter synthesizes
arbiter_msgs = build_arbiter_messages(
    "Check this code for bugs",
    [{"model": r.model, "response": r.content} for r in responses],
)
synthesis = await cfg.llm.chat(
    [ChatMessage(role=m["role"], content=m["content"]) for m in arbiter_msgs],
    model="gemini-3.5-flash",
    temperature=0.3,
)
```

## Free AI Providers

See [docs/free-ai-providers.md](docs/free-ai-providers.md) for 20+ free model providers with signup links, compatible with the `HttpLLMBackend` via [LiteLLM](https://github.com/BerriAI/litellm) proxy.

## License

Apache 2.0
