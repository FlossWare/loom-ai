# ADR-0011: Orchestrator Application Boundary

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #936

## Context

Loom needs one application-facing authority for accepting work, coordinating
Workers and Arbiters, tracking lifecycle state, and returning results with
verification evidence and provenance. If REST, MCP, CLI/TUI, or another adapter
can invoke Workers, Arbiters, or model providers as an alternate workflow path,
execution semantics and persistence can diverge between clients.

The Orchestrator boundary must be independent of HTTP and any particular
programming language. It must also preserve the ownership boundary between
execution coordination and model/provider selection.

## Decision

The AI domain defines an **Orchestrator** as the application service that owns
the lifecycle of submitted Intent executions.

The Orchestrator coordinates Worker execution, Arbiter decisions, verification,
recovery, evidence/provenance collection, and durable lifecycle state through
the relevant contracts. It is the single application-facing authority for
submit, observe, and continue operations.

The Orchestrator is not an HTTP handler, MCP server, CLI/TUI command, model
provider, or model-selection algorithm. Those are adapters or separate
capabilities.

## Application operations

A conforming Orchestrator contract MUST provide semantics equivalent to:

- **Submit:** accept an Intent and return an execution identity/handle plus the
  current observable result or lifecycle state.
- **Observe:** retrieve the lifecycle state, current/final result, failures,
  evidence, and provenance for an execution identity.
- **Continue:** continue an existing execution from its persisted state and
  evidence, preserving the execution identity and relevant history rather than
  requiring a client transcript replay.

An implementation MAY expose additional operations, such as cancellation or
session management, when their lifecycle and authorization semantics are
specified. The operations and representations are language-neutral; the contract
does not mandate method names, HTTP routes, or a particular RPC mechanism.

A production configuration that promises continuation MUST provide durable state
sufficient to reconstruct the required execution context. A non-durable
transport-smoke profile MAY exist, but MUST NOT claim restart-safe continuation.

## Lifecycle and observable state

The Orchestrator MUST make execution lifecycle and terminal outcomes observable.
At minimum, its contract MUST distinguish:

- running or in-progress execution;
- interrupted or resumable execution when applicable;
- successful execution completion;
- failed execution;
- cancelled execution.

A deadline or timeout MUST be represented as an explicit, observable failure or
termination cause; it MUST NOT be reported as successful completion. Additional
states MAY be introduced when their semantics and compatibility mapping are
documented.

Execution status is not the same as task success. The Evaluation and Success
Semantics contract defines whether the requested criteria were met. The
Orchestrator MUST preserve execution facts and evaluation outcomes as distinct
records or fields.

An execution identity MUST remain stable across observation, continuation, and
durable process restart. The state returned by Observe MUST identify the Intent,
execution status, result where available, relevant evidence, provenance, and
state/version information needed by clients to interpret it.

## Single application boundary

REST, MCP, CLI/TUI, and other adapters MUST use the same Orchestrator application
contract for submit, observe, and continue operations.

Adapters MAY validate transport syntax, authenticate/authorize requests, map
representations, and translate errors to transport-specific responses. They MUST
NOT establish a parallel workflow authority by invoking Workers, Arbiters,
verification, or model providers directly.

The REST API is an application boundary over the Orchestrator, not a second
execution engine. MCP and CLI/TUI are clients of that same boundary unless an
implementation explicitly exposes the same Orchestrator interface in-process.

## Worker coordination and verification

The Orchestrator coordinates Workers through the Worker contract. Local and
distributed/fleet Workers MUST be usable behind the same semantic boundary;
deployment topology does not redefine Worker Result semantics.

The Orchestrator MUST preserve Worker failures, requeue/recovery decisions,
verification outcomes, and final evidence. A successful transport response or
successful Worker invocation MUST NOT hide a failed verification or failed task
outcome.

Arbiter policy determines how Worker Results are adjudicated. Evaluation criteria
determine whether the requested task succeeded. The Orchestrator coordinates
these components but MUST NOT collapse them into an implicit success heuristic.

## Ownership boundaries

The Orchestrator owns workflow coordination and execution lifecycle. It does not
own the following concerns:

- **Model/provider/account selection:** owned by the model-router boundary.
- **Profiles, effective configuration, policy, and budget authority:** owned by
  the designated agent-setup/configuration boundary.
- **Provider/model capability claims:** defined by the Model Capability Profile.
- **Provider/model health observations:** defined by the Provider/Model Health
  contract.
- **Execution usage and cost:** defined by Execution Economics.
- **Task-success criteria:** defined by Evaluation and Success Semantics.

The Orchestrator consumes the results of these capabilities through their
contracts. It MUST NOT silently introduce a competing configuration store,
provider selector, or budget authority.

## Failure and cancellation semantics

Failures, cancellation, timeouts/deadlines, recovery decisions, and verification
failures MUST remain observable through the Orchestrator boundary. A client MUST
be able to distinguish a failed execution from an unavailable observation
transport and from a task whose outcome has not yet been evaluated.

Recovery actions MUST follow Recovery Policy and preserve the original execution
identity, prior results, and provenance. Cancellation MUST NOT be rewritten as
ordinary failure or success. A deadline MUST NOT be silently ignored or converted
to success.

The exact API operation for requesting cancellation and the complete deadline
representation require explicit implementation/API contract work; this ADR
requires their observable lifecycle semantics, not a specific route.

## Conformance

An implementation claiming conformance SHOULD test that:

1. submit, observe, and continue use one application service;
2. transport adapters cannot bypass Orchestrator to invoke Workers or providers;
3. execution identity and provenance survive observation and continuation;
4. failure, cancellation, deadline, and verification outcomes remain explicit;
5. durable continuation reconstructs state without transcript replay;
6. local and distributed Workers use the same Worker contract;
7. model selection and effective configuration remain owned by their designated
   external capabilities;
8. transport completion is not conflated with task success.

No HTTP framework, MCP SDK, database, provider SDK, or programming-language API
is normative.

## Consequences

### Positive

- All clients share one execution lifecycle and application boundary.
- Persistence, recovery, verification, and provenance have one authority.
- Provider selection and effective configuration remain independently evolvable.
- Runtime and transport adapters can change without redefining orchestration.

### Negative

- The Orchestrator contract must remain stable across adapters and implementations.
- Durable continuation requires explicit state and versioning semantics.
- Cancellation, deadlines, recovery, and verification need executable conformance
  tests rather than documentation-only claims.

## Non-goals

This ADR does not prescribe a distributed-worker scheduler, a specific REST route
set, a provider/model routing algorithm, or a persistence backend. It does not
claim that every cancellation/deadline operation is implemented today; those are
explicit conformance requirements to complete and test.
