# ADR-001: Execution Tracing and Reasoning Boundary

- **Status:** Accepted
- **Date:** 2026-09-16
- **Related issue:** #946

## Context

Loom executes Workers that may use LLMs, tools, other Workers, and verification steps. Debugging, evaluation, provenance, replay, and auditability require structured evidence of what happened during an execution.

A useful execution trace must expose enough information to reconstruct the execution path and understand important decisions. It should not, however, make Loom dependent on provider-specific model internals or treat a model's private chain-of-thought as an application data model.

## Decision

Loom will provide a provider-independent **ExecutionTrace** abstraction.

An execution trace may contain:

- execution, run, task, and step identifiers
- worker and capability identity
- lifecycle/state transitions
- actions and outcomes
- tool calls and tool results, subject to existing security and redaction rules
- model/provider metadata where applicable
- latency, retry, failure, and cost/token metadata where available
- structured decisions and concise decision rationale
- artifacts and provenance
- verification and evaluation results
- security/policy and sandbox events associated with the execution

Loom will **not** persist, expose, or require access to a model's private chain-of-thought.

When a Worker or model-backed component needs to explain a decision, Loom may record a structured decision or concise rationale suitable for execution provenance. Such rationale is evidence about the execution, not a transcript of hidden model reasoning.

Execution tracing is an architectural capability independent of any particular LLM provider, observability vendor, or Worker implementation.

## Consequences

### Positive

- Executions can be reconstructed from structured evidence rather than log scraping.
- Debugging, evaluation, verification, and audit workflows have a common contract.
- Loom remains provider-neutral.
- Non-LLM Workers can participate in the same trace model.
- Trace data can support replay, evaluation, and future execution optimization without coupling those capabilities to model internals.
- Sensitive reasoning and provider-specific internals do not become a required Loom persistence contract.

### Negative

- Loom needs a durable trace/event model and associated lifecycle semantics.
- Workers and adapters must emit structured execution evidence.
- Trace retention, redaction, and storage require explicit design.
- Decision rationale must remain useful without becoming an informal substitute for private chain-of-thought.

## Scope

This ADR establishes the architectural boundary. The implementation work is tracked in GitHub issue #946.

Provider-specific tracing integrations, OpenTelemetry adapters, persistence formats, and evaluation mechanisms are implementation concerns and may be addressed separately.
