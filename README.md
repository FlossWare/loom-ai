# loom-ai

![loom-ai](docs/assets/banner.svg)

Pluggable AI orchestration framework with swappable backends. Zero required dependencies.

## Install

```bash
pip install flossware-loom-ai              # core (stdlib only)
pip install flossware-loom-ai[server]      # + FastAPI REST server
pip install flossware-loom-ai[postgresql]  # + PostgreSQL/pgvector storage
pip install flossware-loom-ai[redis]       # + Redis queues
pip install flossware-loom-ai[all]         # everything
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
result = await cfg.consensus.synthesize(
    "Explain distributed systems",
    models=["gemini-3.5-flash", "llama-3.3-70b", "mistral-small"],
)
print(result.synthesis.content)
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
| Consensus | `/consensus/*` | `LOOM_LLM_BASE_URL` set |
| Tools | `/tools/*` | `LOOM_TOOLS != disabled` |
| Resources | `/resources/*` | `LOOM_RESOURCES != disabled` |
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
| `LOOM_TOOLS` | `disabled`, `memory` | `disabled` |
| `LOOM_RESOURCES` | `disabled`, `memory` | `disabled` |
| `LOOM_LLM_BASE_URL` | Any OpenAI-compatible URL | *(none)* |
| `LOOM_LLM_API_KEY` | Bearer token | *(none)* |
| `LOOM_LLM_MODEL` | Default model id | `gpt-4o-mini` |
| `LOOM_HOST` | Server bind address | `0.0.0.0` |
| `LOOM_PORT` | Server port | `5000` |

Don't set it? Don't get it. Set nothing at all and you get a pure in-memory orchestrator.

## Architecture

```
loom_ai/
  protocols.py          10 Protocol interfaces (async, stdlib-only)
  models.py             15 dataclasses + 1 enum (Document, Chunk, ChatMessage, Task, etc.)
  config.py             LoomConfig registry with from_env() factory
  consensus.py          ConsensusEngine (fan-out + arbiter synthesis)
  execution.py          ExecutionEngine (DAG-based task scheduling)
  prompts.py            Built-in consensus prompt templates
  server.py             Optional FastAPI REST server
  backends/
    memory.py           In-memory implementations (zero deps)
    memory_mcp.py       In-memory MCP tool/resource providers
    env_secrets.py      Environment variable secrets
    http_llm.py         HTTP LLM backend (urllib, zero deps)
```

## 10 Pluggable Protocols

| Protocol | Purpose | Default | Enterprise |
|----------|---------|---------|------------|
| `StorageBackend` | Documents, chunks, embeddings | In-memory dicts | PostgreSQL + pgvector |
| `QueueBackend` | Named task queues | In-memory deque | Redis |
| `SecretsBackend` | API keys and config | `os.environ` | PostgreSQL encrypted |
| `EmbeddingBackend` | Text to vectors | Zero vectors | OpenAI / Jina / Voyage |
| `SearchBackend` | Full-text + semantic | Substring + cosine | tsvector + pgvector ANN |
| `GraphBackend` | Knowledge graph | Disabled | OrientDB |
| `LLMBackend` | Chat completions | HTTP (any OpenAI-compatible) | Same |
| `ToolProvider` | MCP tool dispatch | In-memory callables | MCP server adapter |
| `ResourceProvider` | MCP resource access | In-memory static | MCP server adapter |
| `TaskRunner` | Task execution strategy | Noop (pass-through) | LLM-backed runner |

## Multi-Model Consensus

Fan out to N models, synthesize with an arbiter:

```python
from loom_ai import LoomConfig

cfg = LoomConfig.from_env()

# High-level: fan-out + arbiter synthesis in one call
result = await cfg.consensus.synthesize(
    "Check this code for bugs",
    models=["gemini-3.5-flash", "llama-3.3-70b", "codestral"],
    arbiter_model="gemini-3.5-flash",
    tool_name="review",
    arbiter_temperature=0.3,
)
print(result.synthesis.content)
print(f"Workers: {len(result.worker_responses)}, Failed: {result.failed_models}")

# Low-level: just fan-out (no arbiter)
from loom_ai import ChatMessage

responses, failed = await cfg.consensus.gather(
    [ChatMessage(role="user", content="Check this code for bugs")],
    models=["gemini-3.5-flash", "llama-3.3-70b", "codestral"],
)
```

## Free AI Providers

See [docs/free-ai-providers.md](docs/free-ai-providers.md) for 20+ free model providers with signup links, compatible with the `HttpLLMBackend` via [LiteLLM](https://github.com/BerriAI/litellm) proxy.

## License

Apache 2.0
