# loom-ai

![loom-ai](docs/assets/banner.svg)

Pluggable AI orchestration framework with swappable backends. Zero required dependencies.

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation, including the extension model, request lifecycle, and implementation boundaries.

Loom is an orchestration substrate built around provider-neutral contracts. The core defines stable interfaces; external projects and services may implement those contracts without becoming Loom dependencies.

```text
                         Loom Core
                            |
             +--------------+--------------+
             |              |              |
        Agent Runtime   Context Engine  Capabilities
             |              |              |
       Goose / native   Headroom /      MCP / native /
       / other agents   native Loom     external tools
             |              |              |
             +--------------+--------------+
                            |
                     Model Providers
              Claude / OpenAI / Gemini /
              Nemotron / Nex-N2 / local
                            |
                    Evaluation Engines
               Loom / G0DM0D3 / Agent Island
```

### Pluggability principles

- **Model Provider** — interchangeable inference/model endpoints.
- **Agent Runtime** — interchangeable agent execution environments.
- **Context Engine** — interchangeable context construction, compression, and cache-aware middleware.
- **Capability/Tool Backend** — interchangeable native, MCP, and external tool implementations.
- **Evaluation Engine** — interchangeable evaluation, ranking, tournament, and benchmark systems.
- **Storage, Queue, Secrets, Embedding, Search, Graph, and Task Runner** remain independently replaceable backends.

External projects are **interoperability targets and implementations**, not architectural dependencies. Loom should define the contract first and validate it against multiple implementations.

This distinction is intentional: Loom can **use** an external project without incorporating it, and can **assimilate** an architectural idea without making the source project a dependency.

## Install

```bash
pip install flossware-loom-ai              # core (stdlib only)
pip install flossware-loom-ai[cli]         # + CLI (loom command)
pip install flossware-loom-ai[server]      # + FastAPI REST server
pip install flossware-loom-ai[postgresql]  # + PostgreSQL/pgvector storage
pip install flossware-loom-ai[redis]       # + Redis queues
pip install flossware-loom-ai[all]         # everything
```

## Configuration

`pip install` adds only the Python client libraries — it does **not** provision
databases or services. You bring your own infrastructure and point loom-ai at it
with environment variables. `LoomConfig.from_env()` reads these at startup.

### Backend selectors

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

### PostgreSQL

Used when `LOOM_STORAGE`, `LOOM_SEARCH`, or `LOOM_SECRETS` is set to `postgresql`.
All three share the same connection pool.

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOM_PG_HOST` | `localhost` | Hostname or IP |
| `LOOM_PG_PORT` | `5432` | Port |
| `LOOM_PG_USER` | `loom` | Database user |
| `LOOM_PG_PASSWORD` | *(empty)* | Password (URL-encoded automatically) |
| `LOOM_PG_DATABASE` | `loom` | Database name |

You can point these at any existing PostgreSQL 12+ instance. The database must
have the following tables pre-created:

- `documents` (id text PK, title text, content text, url text, category text, metadata jsonb, created_at text)
- `chunks` (id text PK, document_id text, content text, chunk_index int, metadata jsonb)
- `embeddings` (id text PK, chunk_id text, vector vector, model text, dimensions int)
- `secrets` (name text PK, value text) — only if using `LOOM_SECRETS=postgresql`

If using `LOOM_SEARCH=postgresql` with semantic search, enable the
[pgvector](https://github.com/pgvector/pgvector) extension (`CREATE EXTENSION vector`).

Loom-ai does not run migrations automatically — you manage the schema with
your own tooling (Alembic, Flyway, plain SQL, etc.).

### Redis

Used when `LOOM_QUEUE=redis`.

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOM_REDIS_URL` | `redis://localhost:6379/0` | Full Redis URL with database number |

Supports any Redis 5+ instance. The URL includes authentication and database selection:

```
redis://user:password@my-redis:6379/2
```

**Queue names are dynamic** — created on the fly when you call `enqueue("my-queue", ...)`.
No upfront configuration needed. All keys are namespaced under the prefix `loom:queue:`
(e.g. `loom:queue:my-queue:pending`), so loom-ai coexists safely with other
applications on the same Redis instance.

Built-in features: priority scoring, lease-based processing (300s default),
retry with exponential backoff (3 max), and automatic dead-letter queue per
queue name. These defaults are configurable when constructing
`RedisQueueBackend` directly (see `lease_timeout`, `max_retries`,
`backoff_base` constructor params).

### OrientDB

Used when `LOOM_GRAPH=orientdb`.

| Variable | Default | Description |
|----------|---------|-------------|
| `ORIENTDB_HOST` | `localhost` | Hostname or IP |
| `ORIENTDB_PORT` | `2424` | Binary protocol port |
| `ORIENTDB_USER` | `root` | Database user |
| `ORIENTDB_PASSWORD` | *(empty)* | Password |
| `ORIENTDB_DB` | `loom_ai` | Database name (must exist) |

Connects to any existing OrientDB 3.x instance. The database must already exist;
loom-ai opens it but does not create it. Vertex/edge classes (`KnowledgeEntity`,
`KnowledgeRelationship`, `Claim`) are created on first insert if they don't exist.

### LLM

Any OpenAI-compatible chat completion endpoint (LiteLLM, vLLM, Ollama, etc.).

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOM_LLM_BASE_URL` | *(unset — LLM disabled)* | Base URL (e.g. `http://litellm:4000/v1`) |
| `LOOM_LLM_API_KEY` | *(empty)* | Bearer token / API key |
| `LOOM_LLM_MODEL` | `gpt-4o-mini` | Default model identifier |
| `LOOM_LLM_PROVIDER` | `openai-compatible` | Provider tag for response parsing |

When `LOOM_LLM_BASE_URL` is unset, the LLM and consensus backends are disabled
(chat/consensus calls will raise). This is fine for storage-only or search-only
usage.

### Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required for `openai`)* | OpenAI API key |

When `LOOM_EMBEDDING=openai`, the `OPENAI_API_KEY` env var must be set.

When `LOOM_EMBEDDING=litellm`, LiteLLM reads provider keys automatically from
standard env vars (`OPENAI_API_KEY`, `COHERE_API_KEY`, `VOYAGE_API_KEY`, etc.)
depending on the model you configure. No loom-specific vars needed.

### Secrets

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOM_SECRETS_FILE` | `.env` | Path to dotenv file (when `LOOM_SECRETS=dotenv`) |
| `LOOM_SECRETS_PREFIX` | *(empty)* | Key prefix filter (e.g. `APP_` makes `get("FOO")` resolve to `APP_FOO`) |

The `env` backend reads directly from `os.environ` (no credentials needed).
The `dotenv` backend reads from a `.env` file, then falls back to `os.environ`.
Both support an optional prefix to namespace your secrets.

### Client SDK / REST

Used by `LoomClient` when connecting to a remote loom-ai server.

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOM_URL` | *(unset)* | Full server URL (e.g. `http://loom:5000`) |
| `LOOM_HOST` | `127.0.0.1` | Server host (used when `LOOM_URL` unset) |
| `LOOM_PORT` | `5000` | Server port |
| `LOOM_API_KEY` | *(empty)* | Bearer token for server auth |
| `LOOM_TIMEOUT` | `60` | Request timeout in seconds |

When `LOOM_URL` is not set, `get_client()` returns a `LocalClient`
(embedded mode, no server needed).  `LOOM_HOST` alone does **not**
trigger remote mode — use `LOOM_URL` for an explicit remote endpoint.

### Security note

Avoid exporting credentials directly in your shell (they end up in
`.bash_history`). Use a `.env` file, a secret manager, or your shell's
secure credential store instead. Loom-ai supports `LOOM_SECRETS=dotenv` for
reading from a `.env` file, and you can plug in any secrets backend (Vault,
AWS Secrets Manager, etc.) via the `SecretsBackend` protocol.

### Examples

**Use an existing PostgreSQL + Redis + LiteLLM proxy:**

```bash
export LOOM_STORAGE=postgresql
export LOOM_SEARCH=postgresql
export LOOM_QUEUE=redis
export LOOM_EMBEDDING=litellm

export LOOM_PG_HOST=db.example.com
export LOOM_PG_DATABASE=myapp
export LOOM_PG_USER=myuser
export LOOM_PG_PASSWORD=secret

export LOOM_REDIS_URL=redis://:redispass@cache.example.com:6379/0

export LOOM_LLM_BASE_URL=http://litellm.example.com:4000/v1
export LOOM_LLM_API_KEY=sk-my-litellm-key
```

**Use existing OrientDB for knowledge graph:**

```bash
export LOOM_GRAPH=orientdb
export ORIENTDB_HOST=graph.example.com
export ORIENTDB_USER=admin
export ORIENTDB_PASSWORD=secret
export ORIENTDB_DB=my_knowledge_graph
```

**Minimal local setup (zero dependencies, zero config):**

```bash
# Nothing to set — all backends default to in-memory/stdlib
python -c "import asyncio; from loom_ai import LoomConfig; asyncio.run(LoomConfig.from_env())"
```

## Quick Start

```python
import asyncio
from loom_ai import LoomConfig, Document

async def main():
    cfg = await LoomConfig.from_env()
    await cfg.storage.store_document(
        Document(id="doc-1", title="Example", content="Hello world")
    )

    result = await cfg.consensus.synthesize(
        "Explain distributed systems",
        models=["gemini-3.5-flash", "llama-3.3-70b", "mistral-small"],
    )
    print(result.synthesis.content)

asyncio.run(main())
```

> **Note:** Consensus requires `LOOM_LLM_BASE_URL` to be set. Without it,
> `cfg.consensus` is `None` and calls to `synthesize()` or `gather()` will
> raise.

## Client SDK

Loom ships a dual-mode client SDK with auto-detection:

```python
from loom_ai.clients import get_client

client = await get_client()
# Returns LocalClient (embedded, no server) when LOOM_URL unset
# Returns LoomClient (REST) when LOOM_URL is set

resp = await client.chat([{"role": "user", "content": "Hello"}])
```

### CLI

```bash
pip install flossware-loom-ai[cli]

loom health                        # check status (auto-detects local/remote)
loom chat "Hello"                  # chat with configured LLM
loom chat "Hello" --stream         # stream response tokens
loom models                        # list available models
loom search "query"                # search knowledge base
loom docs store --title T --file f # store a document
loom docs list                     # list documents
loom docs stats                    # knowledge base stats
loom secrets list                  # list secret names
loom graph add-node "person"       # add a graph node
loom consensus "prompt" --models gemini,gpt-4o,claude
```

### Tool Adapters

Each adapter generates config or env vars to point an AI coding tool at
your loom-ai server. Set `LOOM_URL` and optionally `LOOM_API_KEY` first.

```bash
# Crush
python -m loom_ai.clients.crush              # print config JSON

# OpenCode
python -m loom_ai.clients.opencode           # print config JSON
python -m loom_ai.clients.opencode --env     # print shell exports
python -m loom_ai.clients.opencode --write   # write to config file

# Aider
python -m loom_ai.clients.aider --env        # print shell exports
python -m loom_ai.clients.aider --cmd        # print aider launch command
eval $(python -m loom_ai.clients.aider --env) && aider

# Cursor
python -m loom_ai.clients.cursor             # print config JSON
python -m loom_ai.clients.cursor --env       # print shell exports

# Continue.dev
python -m loom_ai.clients.continue_dev       # print config JSON
python -m loom_ai.clients.continue_dev --write  # write to config file

# Claude Code (MCP bridge)
python -m loom_ai.clients.claude             # print MCP config JSON
python -m loom_ai.clients.claude --env       # print shell exports
python -m loom_ai.clients.claude.mcp_bridge  # run MCP stdio server
```

## Bring Your Own Backend

Every loom-ai backend is a small async interface defined with `typing.Protocol`.
To swap in your own database, queue, graph store, or anything else:

1. Write a class whose methods match the protocol signatures
2. Pass the instance to `LoomConfig`

No inheritance, no registration, no framework imports required.

| Want to use... | Implement | Methods |
|----------------|-----------|---------|
| MongoDB, DynamoDB, S3 | `StorageBackend` | 13 |
| RabbitMQ, Kafka, SQS | `QueueBackend` | 6 |
| Vault, AWS Secrets Manager | `SecretsBackend` | 4 |
| Cohere, Voyage AI, local ONNX | `EmbeddingBackend` | 4 |
| Elasticsearch, Meilisearch | `SearchBackend` | 5 |
| Neo4j, ArangoDB, TigerGraph | `KnowledgeGraph` | 10 |
| Ollama, vLLM, custom server | `LLMBackend` | 3 |

```python
class MyQueue:
    async def enqueue(self, queue_name, items): ...
    async def fetch(self, queue_name, count, worker_id): ...
    async def complete(self, queue_name, item_id): ...
    async def requeue(self, queue_name, items): ...
    async def status(self, queue_name): ...
    async def list_queues(self): ...

cfg = LoomConfig(queue=MyQueue(), ...)
```

See [docs/architecture.md](docs/architecture.md#extension-model) for the full extension guide with examples for LLM, queue, graph, and secrets backends.

## Protocol Contracts

Loom defines **81 `@runtime_checkable` Protocol contracts** across 12 modules, all using structural subtyping (no ABC inheritance required). The recommended import path is `from loom_ai.contracts import ...` which re-exports every contract through a single stable facade. See [docs/contracts.md](docs/contracts.md) for the full inventory.

### Core Protocols (`protocols.py`)

| Protocol | Purpose | Default Backend |
|----------|---------|-----------------|
| `StorageBackend` | Documents, chunks, embeddings | In-memory dicts |
| `QueueBackend` | Named task queues | In-memory deque |
| `SecretsBackend` | API keys and config | `os.environ` |
| `EmbeddingBackend` | Text to vectors | Zero vectors |
| `SearchBackend` | Full-text + semantic | Substring + cosine |
| `KnowledgeGraph` | Knowledge graph | In-memory adjacency |
| `LLMBackend` | Chat completions | HTTP (OpenAI-compatible) |
| `ToolProvider` | MCP-shaped tool contract | In-memory callables |
| `ResourceProvider` | MCP-shaped resource contract | In-memory static |
| `TaskRunner` | Task execution strategy | Noop (pass-through) |
| `IdempotentStore` | Upsert semantics marker | All storage backends |

### Core, Workflow, Session: Orchestration Contracts (21 contracts)

Structured output, conversation, memory, model routing, consensus patterns, knowledge/RAG, streaming, workflow, learning, strategy selection, budget tracking, transcripts, resilience (circuit breaker), observability, session management, worker registry, caching, evaluation, feedback loops, and human-in-the-loop.

### Graph through Context: Advanced Contracts (43 contracts)

Knowledge graphs, temporal stores, belief management, evaluation suites, telemetry, inference routing, agent lifecycle, agent memory, output validation, security gates, program optimization, agent loops, recipe execution, ACP interoperability, context assembly, trajectory stores, agent environments, provider/capability/policy registries, catalog synchronization, tournament runners, consensus strategies, model evaluation, context compression, prompt cache optimization, pluggable runtimes, health checks, and request validation.

### Execution Contracts (`contracts_execution.py`, 3 contracts)

Execution steps, sequential pipeline with cancellation/deadlines, and execution observers.

### REST API Contracts (`contracts_api.py`, 3 contracts)

Request lifecycle, error handling, and middleware protocols.

## Backend Implementations

Pluggable backend modules in `loom_ai/backends/`:

| Backend | Purpose |
|---------|---------|
| `adversarial` | Independent model panel verification |
| `consensus_strategies` | Majority vote, weighted, quality threshold |
| `fleet` | Worker pool + 3 load-balancing strategies |
| `genetic_optimizer` | GA-based strategy parameter optimization |
| `graph` | In-memory knowledge graph with BFS/DFS |
| `postgresql` | PostgreSQL + pgvector storage/search |
| `rag` | Document ingestion, embeddings, hybrid search |
| `redis_queue` | Durable queue with priorities, leases, DLQ |
| `security` | Config validation, secret masking, audit logging |
| `task_classifier` | Rule-based task classification + blueprints |
| `telemetry` | Execution telemetry, cost tracking, model feedback |

> **Note:** Model routing (`adaptive_router`, `free_model_router`, `provider_health`, `provider_discovery`) has been extracted to [model-router-ai](https://github.com/FlossWare/model-router-ai).

See `examples/demo.py` for a runnable walkthrough using in-memory backends.

## Multi-Model Consensus

```python
import asyncio
from loom_ai import ChatMessage, LoomConfig

async def main():
    cfg = await LoomConfig.from_env()

    result = await cfg.consensus.synthesize(
        "Check this code for bugs",
        models=["gemini-3.5-flash", "llama-3.3-70b", "codestral"],
        arbiter_model="gemini-3.5-flash",
        tool_name="review",
        arbiter_temperature=0.3,
    )
    print(result.synthesis.content)

    responses, failed = await cfg.consensus.gather(
        [ChatMessage(role="user", content="Check this code for bugs")],
        models=["gemini-3.5-flash", "llama-3.3-70b", "codestral"],
    )

asyncio.run(main())
```

The arbiter uses the same configured deadline/retry policy as worker calls and returns successful worker responses when synthesis cannot be completed.

## License

Apache 2.0
