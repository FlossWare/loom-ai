# Loom Architecture

Loom is an orchestration substrate, not an agent framework.  Provider-neutral
contracts define the API; backends implement them.  Any backend can be swapped
without changing core semantics.

For installation, quick-start examples, and the full protocol table see the
[README](../README.md).

---

## Layered Architecture

```text
+-------------------------------------+
|        Application Layer            |
|  (Agent runtimes, user code, CLI)   |
+-------------------------------------+
|       Orchestration Layer           |
|  (Consensus, routing, execution)    |
+-------------------------------------+
|         Contract Layer              |
|  (Protocol interfaces)             |
+-------------------------------------+
|          Backend Layer              |
|  (In-memory, PostgreSQL, Redis)     |
+-------------------------------------+
```

**Application layer** -- user code, agent runtimes (Goose, custom agents),
REST clients, and CLI tools.  This layer depends on contracts and optionally
on orchestration components like `ConsensusEngine`.

**Orchestration layer** -- `ConsensusEngine` (multi-model fan-out with arbiter
synthesis), `ExecutionEngine` (DAG-based task scheduling), and higher-level
coordination such as adaptive routing and fleet management.  These components
depend on the contract layer but never on a specific backend.

**Contract layer** -- 78 `@runtime_checkable` Protocol classes across
`protocols.py` and `contracts_phase1.py` through `contracts_phase9.py` plus
`contracts_api.py`.  Nearly all methods are `async` (exceptions include
`IdempotentStore.is_idempotent`).  The only imports are from the
standard library (`typing`, `dataclasses`).

**Backend layer** -- 36 pluggable modules in `loom_ai/backends/` that satisfy
contracts via structural subtyping.  Each module can depend on an external
library (asyncpg, redis, etc.) but the dependency is optional and loaded
lazily.

---

## Core Contracts vs Implementations

Contracts and implementations live in separate packages and depend in one
direction only.

```text
loom_ai/protocols.py          <-- 11 core Protocol classes
loom_ai/contracts_phase1.py   <-- 7 orchestration contracts (phase 1)
loom_ai/contracts_phase2.py   <-- 8 orchestration contracts (phase 2)
...                           <-- phases 3-9, contracts_api.py
loom_ai/models.py             <-- plain dataclasses (Document, ChatMessage, ...)
loom_ai/models_phase1.py      <-- phase-specific data models
...
loom_ai/backends/memory.py    <-- in-memory implementations
loom_ai/backends/postgresql.py
loom_ai/backends/redis_queue.py
loom_ai/backends/http_llm.py
...                           <-- 36 backend modules total
```

Contracts use `typing.Protocol` with `@runtime_checkable`:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMBackend(Protocol):
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse: ...

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...

    async def list_models(self) -> list[str]: ...
```

Implementations satisfy contracts through structural subtyping -- they match
the method signatures without importing or inheriting from the Protocol class.
The in-memory backends import models (`ChatMessage`, `ChatResponse`) for type
annotations, but never import the Protocol itself at runtime.

---

## Dependency Direction

```text
contracts  -->  nothing (stdlib only)
models     -->  nothing (stdlib only)
backends   -->  models (for type hints)
             +-> contracts (TYPE_CHECKING only, for docstring cross-refs)
             +-> optional third-party lib (asyncpg, redis, etc.)
config     -->  protocols + backends (lazy imports)
consensus  -->  protocols + models + prompts
execution  -->  protocols + models + config
server     -->  config + models (FastAPI optional dependency)
```

External projects can implement any Loom contract without depending on the
`loom_ai` package at all.  A class that structurally matches `LLMBackend` is
a valid `LLMBackend`, even if `loom_ai` is never installed.

---

## LoomConfig -- Central Registry

`LoomConfig` is a `@dataclass` that wires every backend together in one place.
There are two construction paths:

**Explicit injection** (testing, custom setups):

```python
from loom_ai import LoomConfig

cfg = LoomConfig(
    storage=my_storage,
    queue=my_queue,
    secrets=my_secrets,
    embedding=my_embedding,
    search=my_search,
    graph=my_graph,          # optional, None to disable
    llm=my_llm,              # optional, None if no LLM configured
)
```

**Environment-based auto-detection** (`LoomConfig.from_env()`):

```python
cfg = await LoomConfig.from_env()  # async -- some backends need await
```

Reads `LOOM_*` environment variables and lazily imports the appropriate
backend.  Defaults to stdlib-only in-memory backends when no variables are set.

| Variable            | Options                          | Default     |
|---------------------|----------------------------------|-------------|
| `LOOM_STORAGE`      | `memory`, `postgresql`           | `memory`    |
| `LOOM_QUEUE`        | `memory`, `redis`                | `memory`    |
| `LOOM_SECRETS`      | `env`, `dotenv`, `postgresql`    | `env`       |
| `LOOM_EMBEDDING`    | `noop`, `openai`, `litellm`      | `noop`      |
| `LOOM_SEARCH`       | `memory`, `postgresql`           | `memory`    |
| `LOOM_GRAPH`        | `disabled`, `memory`, `orientdb` | `disabled`  |
| `LOOM_LLM_BASE_URL` | Any OpenAI-compatible URL        | (unset)     |
| `LOOM_LLM_API_KEY`  | Bearer token                     | `""`        |
| `LOOM_LLM_MODEL`    | Model id                         | `gpt-4o-mini` |
| `LOOM_TOOLS`        | `disabled`, `memory`             | `disabled`  |
| `LOOM_RESOURCES`    | `disabled`, `memory`             | `disabled`  |

When `LOOM_LLM_BASE_URL` is set, `LoomConfig` also creates a `ConsensusEngine`
wrapping the LLM backend automatically.

---

## Request Lifecycle

A typical multi-model consensus request flows through these stages:

```text
1. Request arrives
   (REST API via server.py, or direct Python call)
        |
2. ConsensusEngine.synthesize()
        |
   +----+----+
   |         |
3. Fan-out: send prompt to N models in parallel
   via LLMBackend.chat(), with:
   - asyncio.Semaphore concurrency limiting
   - deadline-based timeouts
   - exponential backoff + jitter on retryable errors (429, 5xx)
        |
4. Collect responses, track failed models
        |
5. Arbiter synthesis
   Build arbiter prompt from worker responses (loom_ai.prompts)
   Call LLMBackend.chat() for the arbiter model
   Same retry/deadline policy as worker calls
        |
6. Return ConsensusResult
   - synthesis: ChatResponse (arbiter output)
   - worker_responses: list[ChatResponse]
   - failed_models: list[str]
   - arbiter_attempted: bool
   - arbiter_error: str | None
```

### Execution Hierarchy

Loom's execution layer is composed of three complementary levels that form
a clear hierarchy:

```text
ExecutionEngine              (DAG orchestration, topological waves)
  └── SequentialExecutionPipeline  (sequential step runner)
       └── TaskRunner              (single task execution primitive)
```

**TaskRunner** (`loom_ai/protocols.py`) -- the lowest-level primitive.  Runs
a single `Task` through a configured backend (e.g. `LLMTaskRunner`,
`NoopTaskRunner`) and returns a result.  This is the unit of work.

**ExecutionPipeline / SequentialExecutionPipeline**
(`loom_ai/contracts_execution.py`, `loom_ai/backends/execution_pipeline.py`) --
runs a flat sequence of `ExecutionStep` objects one at a time.  Provides
operational lifecycle support: cancellation between steps, ISO-8601 deadline
enforcement, fail-fast vs continue-on-error modes, and observer notifications
at each step boundary.  This is a sequential runner, not a DAG orchestrator.

**ExecutionEngine** (`loom_ai/execution.py`) -- the highest-level component.
Accepts an `ExecutionPlan` containing tasks with explicit dependency edges,
performs topological sorting, and executes independent tasks concurrently in
waves via `asyncio.gather`.  A failed task cancels its pending transitive
dependents without blocking independent branches of the DAG.

These layers are complementary, not competing.  `ExecutionEngine` decomposes a
DAG into sequential waves of concurrent tasks; `SequentialExecutionPipeline`
(or a similar `ExecutionPipeline` implementation) can run each wave's steps
with deadline and cancellation support.  `TaskRunner` is the leaf-level
executor used by both.

---

## Extension Model

Loom is designed to be extended by adding new backend implementations.  The
steps below walk through adding a custom `LLMBackend` as a concrete example,
but the same pattern applies to all 11 core protocols and the phase contracts.

### Step 1: Pick the Protocol

Identify the contract you want to implement.  The core contracts live in
`loom_ai/protocols.py`:

- `StorageBackend` -- document/chunk/embedding persistence
- `QueueBackend` -- named task queues
- `SecretsBackend` -- API key storage
- `EmbeddingBackend` -- text-to-vector generation
- `SearchBackend` -- full-text + semantic search
- `GraphBackend` -- knowledge graph
- `LLMBackend` -- chat completions
- `ToolProvider` -- MCP-shaped tool dispatch
- `ResourceProvider` -- MCP-shaped resource access
- `TaskRunner` -- task execution strategy
- `IdempotentStore` -- upsert semantics marker

### Step 2: Write a class with matching method signatures

No imports from `loom_ai` are required at runtime.  Your class just needs to
have methods with the right names, signatures, and return types.

```python
# my_llm_backend.py -- zero loom_ai imports at runtime

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ChatMessage:
    role: str
    content: str

@dataclass
class ChatResponse:
    content: str
    model: str = ""
    provider: str = ""
    usage: dict = None

    def __post_init__(self):
        if self.usage is None:
            self.usage = {}


class MyCustomLLM:
    """Custom LLM backend -- satisfies LLMBackend via structural subtyping."""

    async def chat(
        self,
        messages: list,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        # Your implementation here
        return ChatResponse(content="hello", model=model or "my-model")

    async def chat_stream(
        self,
        messages: list,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        resp = await self.chat(messages, model=model)
        for word in resp.content.split():
            yield word + " "

    async def list_models(self) -> list[str]:
        return ["my-model"]
```

If you prefer type safety and are comfortable depending on `loom_ai`, you can
import the model dataclasses directly:

```python
from loom_ai.models import ChatMessage, ChatResponse
```

But this is optional.  Structural subtyping means the contract is enforced by
method shape, not by import graph.

### Step 3: Verify structural compatibility

You can use `isinstance` to check protocol conformance at runtime:

```python
from loom_ai.protocols import LLMBackend

backend = MyCustomLLM()
assert isinstance(backend, LLMBackend)  # True -- structural match
```

### Step 4: Pass the instance to LoomConfig

```python
from loom_ai import LoomConfig

cfg = LoomConfig(
    storage=...,
    queue=...,
    secrets=...,
    embedding=...,
    search=...,
    llm=MyCustomLLM(),
)
```

The consensus engine, execution engine, and REST server will all use your
backend transparently.

### Step 5 (optional): Register in from_env()

To make your backend selectable via `LOOM_*` environment variables, add a case
to the appropriate `_build_*` method in `loom_ai/config.py`.  Use lazy imports
to keep the core dependency-free:

```python
@staticmethod
def _build_llm() -> LLMBackend | None:
    base_url = os.environ.get("LOOM_LLM_BASE_URL")
    if not base_url:
        return None

    provider = os.environ.get("LOOM_LLM_PROVIDER", "openai-compatible")
    if provider == "my-custom":
        from my_llm_backend import MyCustomLLM
        return MyCustomLLM()

    from loom_ai.backends.http_llm import HttpLLMBackend
    return HttpLLMBackend(base_url=base_url, ...)
```

---

## MCP Interoperability

Loom defines `ToolProvider` and `ResourceProvider` contracts that are
MCP-shaped but transport-neutral.

```python
@runtime_checkable
class ToolProvider(Protocol):
    async def list_tools(self) -> list[ToolDefinition]: ...
    async def call_tool(self, name: str, arguments: dict) -> ToolResult: ...

@runtime_checkable
class ResourceProvider(Protocol):
    async def list_resources(self) -> list[ResourceDefinition]: ...
    async def read_resource(self, uri: str) -> ResourceContent: ...
```

The data models (`ToolDefinition`, `ToolResult`, `ResourceDefinition`,
`ResourceContent`) mirror MCP's JSON-Schema-shaped tool/resource descriptors.

An MCP SDK adapter can bridge these contracts to a real MCP server or client.
The core `loom_ai` package has no MCP transport dependency -- it defines the
shape of the interaction, not the wire protocol.

The shipped `MemoryToolProvider` and `MemoryResourceProvider` in
`loom_ai/backends/memory_mcp.py` provide in-memory implementations for testing
and local development.

---

## Idempotency Contract

Backends that implement `IdempotentStore` guarantee:

1. **Same result** -- calling a write method twice with identical arguments
   produces the same observable state as calling it once.
2. **No duplicates** -- repeated calls never create duplicate records.
3. **Safe retries** -- HTTP handlers, queue workers, and cron jobs can safely
   retry without additional deduplication logic.

All shipped storage and search backends satisfy this contract.  `QueueBackend`
intentionally does not -- `enqueue` appends duplicates by design.

---

## Contract Phases

The 78 protocol contracts are organized into phases reflecting the order they
were designed:

| Phase | File | Count | Focus |
|-------|------|-------|-------|
| Core | `protocols.py` | 11 | Storage, queue, secrets, LLM, tools, graph |
| API | `contracts_api.py` | 3 | Request lifecycle, error handling, middleware |
| 1 | `contracts_phase1.py` | 7 | Structured output, conversation, memory, router, RAG |
| 2 | `contracts_phase2.py` | 8 | Workflow, learning, strategy, budget, resilience |
| 3 | `contracts_phase3.py` | 6 | Session, worker registry, cache, evaluation |
| 4 | `contracts_phase4.py` | 5 | Knowledge graphs, temporal stores, beliefs |
| 5 | `contracts_phase5.py` | 8 | Eval suites, telemetry, agent lifecycle, security |
| 6 | `contracts_phase6.py` | 7 | Agent loops, recipes, ACP, context, trajectories |
| 7 | `contracts_phase7.py` | 4 | Provider/capability/policy registries, catalog sync |
| 8 | `contracts_phase8.py` | 9 | Tournaments, consensus strategies, evaluation |
| 9 | `contracts_phase9.py` | 10 | Context compression, prompt cache, runtimes, health |

Phases are additive -- later phases never modify earlier contracts.  Each phase
has a corresponding `models_phaseN.py` with its data models.

---

## Implementation Boundaries

What Loom **is**:

- An orchestration substrate with stable, protocol-based contracts
- Provider-neutral -- works with any OpenAI-compatible API endpoint
- A consensus engine that fans out to multiple models and synthesizes
- A DAG execution engine for task scheduling with dependency tracking
- A plugin system where backends are swapped at configuration time

What Loom **is not**:

- An agent framework (it provides primitives that agent runtimes use)
- A model serving platform (it calls external APIs)
- An MCP server or client (it defines MCP-shaped contracts only)
- A training or fine-tuning system (it orchestrates pre-trained models)

Loom defines the contract first and validates it against multiple
implementations.  External projects are interoperability targets, not
architectural dependencies.
