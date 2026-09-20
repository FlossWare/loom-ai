# Loom Core Qualification

## Purpose

This is the qualification phase for Loom as a general-purpose AI orchestration substrate.

It is intentionally separate from application-specific workloads such as FlossWare web scraping.

The immediate goal is to demonstrate that a developer can use Loom to build and run a useful agent workflow, understand what Loom is doing, and rely on its core contracts without first adopting a large application stack.

## What is in scope

A successful qualification exercises the core Loom path:

```text
agent
  -> model selection/routing
  -> tool discovery and invocation
  -> orchestration / multi-step execution
  -> state and memory
  -> MCP where applicable
  -> verification / failure handling
  -> observability / evidence
  -> API or CLI consumer
```

The workflow should be useful enough to expose awkward APIs and missing abstractions, rather than merely proving that individual functions can be called.

## What is explicitly out of scope

- FlossWare web scraping
- Discovery/acquisition/chunking pipelines specific to FlossWare
- New roadmap features that are not required by the qualification workflow
- Synthetic memory systems created solely for demonstration

Scraping remains an important downstream workload. It is deferred here so it does not become the gate for making Loom understandable and shareable.

## Qualification workflow

Use a small, deterministic engineering task against a real repository or fixture repository.

1. Start a fresh Loom consumer.
2. Give the agent a concrete engineering task.
3. Allow it to inspect the repository through Loom tools.
4. Require it to make an appropriate change.
5. Require relevant verification, including tests where applicable.
6. Capture task, tool, model, decision, verification, and outcome evidence.
7. Persist the useful state/knowledge through Loom's existing persistence abstractions.
8. Terminate the process completely.
9. Start a new process with no prior transcript.
10. Recover the persisted knowledge with provenance.
11. Give the new process a follow-up task that depends on the recovered knowledge.
12. Verify that the follow-up succeeds without replaying the original transcript.

## Hard gates

The qualification does not pass merely because an agent produced plausible text.

- A failed verification must not be reported as a successful engineering outcome.
- Tool failures must be represented and recoverable rather than silently swallowed.
- State needed across the session boundary must be durable.
- Recovered knowledge must retain provenance sufficient to explain where it came from.
- The consumer must use Loom's public contracts rather than reaching into implementation details.
- The workflow must be reproducible by another developer.

## Shareable outcome

The resulting demonstration should answer these questions quickly:

1. What problem does Loom solve?
2. How does an application create/use an agent?
3. How are models and tools abstracted?
4. How does Loom handle multi-step work and failures?
5. What survives process death?
6. How does another application consume Loom?

A person unfamiliar with the project should be able to run the workflow and understand the value without reading the implementation first.

## Relationship to other dogfood work

There are two separate validation tracks:

**Loom core qualification**

> Does Loom itself provide a coherent, reliable foundation for AI-agent applications?

**Application dogfooding**

> Can a real application, such as FlossWare scraping or `personal-agent`, use Loom to perform meaningful work?

Core qualification comes first for the current milestone. Application dogfooding follows and should generate the next round of real-world Loom requirements.

## Exit condition

This phase is complete when the workflow has been executed successfully by a fresh consumer, including the process-death/session-boundary test, and the resulting demo/documentation is suitable for sharing with engineers outside the project.
