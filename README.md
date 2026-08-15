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

```python
from loom_ai import LoomConfig, Document

cfg = LoomConfig.from_env()
await cfg.storage.store_document(
    Document(id="doc-1", title="Example", content="Hello world")
)

result = await cfg.consensus.synthesize(
    "Explain distributed systems",
    models=["gemini-3.5-flash", "llama-3.3-70b", "mistral-small"],
)
print(result.synthesis.content)
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
| `ToolProvider` | MCP-shaped tool contract | In-memory callables | MCP transport adapter |
| `ResourceProvider` | MCP-shaped resource contract | In-memory static | MCP transport adapter |
| `TaskRunner` | Task execution strategy | Noop (pass-through) | LLM-backed runner |

The MCP-related protocols define **Loom contracts** for tools and resources. They are transport-neutral. An MCP SDK, server, or transport adapter can be added without making MCP transport a dependency of Loom core.

`LLMTaskRunner` is a minimal reference implementation of `TaskRunner`. Richer agent behavior such as planning, tool loops, verification, and application-specific interaction belongs above this execution layer.

## Multi-Model Consensus

```python
from loom_ai import ChatMessage, LoomConfig

cfg = LoomConfig.from_env()

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
```

The arbiter uses the same configured deadline/retry policy as worker calls and returns successful worker responses when synthesis cannot be completed.

## License

Apache 2.0
