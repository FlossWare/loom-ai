#!/usr/bin/env python3
"""Loom-AI framework demo -- runnable without external dependencies.

This example demonstrates the core capabilities of the loom-ai
orchestration framework using only in-memory backends.  No database,
no API keys, and no network access required.

Sections
--------
1. **Configuration** -- wire up in-memory backends via LoomConfig
2. **LLM backend** -- a stub LLM that echoes responses for demonstration
3. **Consensus** -- fan-out a prompt to multiple "models" and synthesize
4. **Knowledge pipeline** -- ingest documents and query by keyword
5. **Persistent memory** -- store, recall, search, and forget memories
6. **Workflow execution** -- run a DAG of tasks with dependencies

Run with::

    python examples/demo.py
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from loom_ai.backends.knowledge import InMemoryKnowledgePipeline, TokenChunker
from loom_ai.backends.memory import (
    InMemoryPersistentMemory,
    MemoryGraphBackend,
    MemoryQueueBackend,
    MemorySearchBackend,
    MemoryStorageBackend,
    NoopEmbeddingBackend,
)
from loom_ai.config import LoomConfig
from loom_ai.consensus import ConsensusEngine
from loom_ai.execution import ExecutionEngine, NoopTaskRunner
from loom_ai.models import (
    ChatMessage,
    ChatResponse,
    ExecutionPlan,
    Task,
    TaskStatus,
)

# ======================================================================
# 1. Stub LLM backend (no real API calls)
# ======================================================================


class StubLLMBackend:
    """A fake LLM backend that returns canned responses.

    Each "model" produces a slightly different answer so the consensus
    engine has material to synthesize.  This satisfies the LLMBackend
    protocol without requiring any network access.
    """

    _RESPONSES: dict[str, str] = {
        "model-alpha": (
            "The best approach is to use a modular architecture "
            "with clear protocol boundaries."
        ),
        "model-beta": (
            "I recommend a plugin-based design with dependency "
            "injection for maximum flexibility."
        ),
        "model-gamma": (
            "A layered architecture with well-defined interfaces "
            "provides the best maintainability."
        ),
    }

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Return a canned response based on the model id."""
        _ = temperature
        _ = max_tokens
        model = model or "model-alpha"
        content = self._RESPONSES.get(
            model,
            f"[{model}] Response to: {messages[-1].content[:80]}",
        )
        return ChatResponse(content=content, model=model, provider="stub")

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield the response word by word."""
        _ = max_tokens
        resp = await self.chat(messages, model=model, temperature=temperature)
        for word in resp.content.split():
            yield word + " "

    async def list_models(self) -> list[str]:
        """Return the available stub model ids."""
        return sorted(self._RESPONSES.keys())


# ======================================================================
# 2. Wire up LoomConfig with all in-memory backends
# ======================================================================


def build_config() -> LoomConfig:
    """Create a fully wired LoomConfig using only in-memory backends.

    This is the "crush" deployment profile -- zero external dependencies,
    suitable for testing, demos, and local development.
    """
    llm = StubLLMBackend()
    from loom_ai.backends.env_secrets import EnvSecretsBackend

    return LoomConfig(
        storage=MemoryStorageBackend(),
        queue=MemoryQueueBackend(),
        secrets=EnvSecretsBackend(),
        embedding=NoopEmbeddingBackend(),
        search=MemorySearchBackend(),
        graph=MemoryGraphBackend(),
        llm=llm,
        consensus=ConsensusEngine(llm),
    )


# ======================================================================
# 3. Demonstrate consensus across multiple models
# ======================================================================


async def demo_consensus(config: LoomConfig) -> None:
    """Fan out a design question to three stub models, then synthesize.

    The ConsensusEngine sends the same prompt to all models in parallel,
    collects their responses, and asks an "arbiter" model to synthesize
    a single definitive answer.
    """
    print("=" * 60)
    print("CONSENSUS DEMO")
    print("=" * 60)

    assert config.consensus is not None
    result = await config.consensus.synthesize(
        prompt="What architecture should we use for a plugin system?",
        models=["model-alpha", "model-beta", "model-gamma"],
        arbiter_model="model-alpha",
        tool_name="design",
    )

    print(f"\nWorker responses collected: {len(result.worker_responses)}")
    for i, resp in enumerate(result.worker_responses, 1):
        print(f"  Model {i} ({resp.model}): {resp.content[:60]}...")

    print(f"\nFailed models: {result.failed_models or 'none'}")
    print(f"Arbiter attempted: {result.arbiter_attempted}")
    print(f"Synthesis: {result.synthesis.content[:120]}...")
    print()


# ======================================================================
# 4. Demonstrate the knowledge pipeline (RAG)
# ======================================================================


async def demo_knowledge_pipeline() -> None:
    """Ingest documents and retrieve relevant chunks by keyword query.

    The InMemoryKnowledgePipeline chunks text using the TokenChunker,
    then scores chunks by keyword frequency for retrieval.
    """
    print("=" * 60)
    print("KNOWLEDGE PIPELINE DEMO")
    print("=" * 60)

    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)

    # Ingest a few documents on different topics.
    doc1 = await pipeline.ingest(
        "Python is a high-level programming language known for its "
        "readability and versatility. Python supports multiple "
        "programming paradigms including procedural, object-oriented, "
        "and functional programming.",
        metadata={"topic": "python"},
    )
    print(f"Ingested document 1: {doc1}")

    doc2 = await pipeline.ingest(
        "PostgreSQL is a powerful open-source relational database. "
        "It supports advanced features like JSON columns, full-text "
        "search, and the pgvector extension for similarity search.",
        metadata={"topic": "databases"},
    )
    print(f"Ingested document 2: {doc2}")

    doc3 = await pipeline.ingest(
        "Machine learning models can be served via REST APIs. "
        "Common frameworks include FastAPI for Python web servers "
        "and various model serving platforms.",
        metadata={"topic": "ml-ops"},
    )
    print(f"Ingested document 3: {doc3}")

    # Query the pipeline.
    results = await pipeline.query("Python programming", limit=3)
    print(f"\nQuery: 'Python programming' -> {len(results)} results")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] score={r.score:.1f}  source={r.source[:8]}...")
        print(f"      {r.content[:70]}...")

    results = await pipeline.query("PostgreSQL database", limit=2)
    print(f"\nQuery: 'PostgreSQL database' -> {len(results)} results")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] score={r.score:.1f}  {r.content[:70]}...")
    print()


# ======================================================================
# 5. Demonstrate persistent memory
# ======================================================================


async def demo_persistent_memory() -> None:
    """Store, recall, search, update, and forget named memories.

    The InMemoryPersistentMemory backend keeps typed key-value memories
    that persist for the lifetime of the process.
    """
    print("=" * 60)
    print("PERSISTENT MEMORY DEMO")
    print("=" * 60)

    mem = InMemoryPersistentMemory()

    # Store some memories.
    await mem.store(
        "project-goal",
        "Build a pluggable AI orchestration framework",
        memory_type="objective",
        metadata={"priority": "high"},
    )
    await mem.store(
        "db-choice",
        "PostgreSQL with pgvector for embeddings",
        memory_type="decision",
    )
    await mem.store(
        "api-style",
        "Use async protocols with structural subtyping",
        memory_type="decision",
    )

    # Recall by name.
    goal = await mem.recall("project-goal")
    assert goal is not None
    print(f"Recalled '{goal.name}': {goal.content}")
    print(f"  type={goal.memory_type}  metadata={goal.metadata}")

    # Search across memories.
    decisions = await mem.search("", memory_type="decision")
    print(f"\nAll 'decision' memories: {len(decisions)}")
    for d in decisions:
        print(f"  - {d.name}: {d.content}")

    results = await mem.search("PostgreSQL")
    print(f"\nSearch 'PostgreSQL': {len(results)} match(es)")

    # Update a memory.
    await mem.update(
        "db-choice",
        "PostgreSQL with pgvector and full-text search",
        metadata={"reviewed": True},
    )
    updated = await mem.recall("db-choice")
    assert updated is not None
    print(f"\nUpdated '{updated.name}': {updated.content}")

    # Forget a memory.
    forgotten = await mem.forget("api-style")
    print(f"\nForgot 'api-style': {forgotten}")
    remaining = await mem.list_memories()
    print(f"Remaining memories: {len(remaining)}")
    print()


# ======================================================================
# 6. Demonstrate workflow execution (task DAG)
# ======================================================================


async def demo_workflow(config: LoomConfig) -> None:
    """Execute a DAG of tasks with dependencies using the ExecutionEngine.

    Tasks run in topological waves -- independent tasks execute in
    parallel, and downstream tasks wait for their dependencies.
    """
    print("=" * 60)
    print("WORKFLOW EXECUTION DEMO")
    print("=" * 60)

    # Build a simple task DAG:
    #   fetch-data  ->  process-data  ->  generate-report
    #   validate    ->  process-data
    plan = ExecutionPlan(
        id="demo-plan",
        tasks=[
            Task(
                id="fetch-data",
                name="Fetch Data",
                description="Retrieve raw data from source",
                input_data={"source": "demo-api"},
            ),
            Task(
                id="validate",
                name="Validate Schema",
                description="Validate the data schema",
                input_data={"schema": "v2"},
            ),
            Task(
                id="process-data",
                name="Process Data",
                description="Transform and clean the data",
                dependencies=["fetch-data", "validate"],
                input_data={"format": "json"},
            ),
            Task(
                id="generate-report",
                name="Generate Report",
                description="Create the final report",
                dependencies=["process-data"],
                input_data={"template": "summary"},
            ),
        ],
    )

    engine = ExecutionEngine(config, runner=NoopTaskRunner())

    print(f"Plan '{plan.id}' has {len(plan.tasks)} tasks")
    print("Dependencies:")
    for t in plan.tasks:
        deps = ", ".join(t.dependencies) if t.dependencies else "(none)"
        print(f"  {t.id} <- {deps}")

    completed_plan = await engine.execute_plan(plan)

    print("\nExecution results:")
    for t in completed_plan.tasks:
        status_label = t.status.value.upper()
        print(f"  [{status_label:>9}] {t.name}")
        if t.output_data:
            print(f"             output keys: {list(t.output_data.keys())}")

    all_completed = all(t.status == TaskStatus.COMPLETED for t in completed_plan.tasks)
    print(f"\nAll tasks completed: {all_completed}")
    print()


# ======================================================================
# Main
# ======================================================================


async def main() -> None:
    """Run all demos sequentially."""
    print()
    print("Loom-AI Framework Demo")
    print("No external dependencies required -- everything runs in-memory.")
    print()

    config = build_config()

    await demo_consensus(config)
    await demo_knowledge_pipeline()
    await demo_persistent_memory()
    await demo_workflow(config)

    print("=" * 60)
    print("All demos completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
