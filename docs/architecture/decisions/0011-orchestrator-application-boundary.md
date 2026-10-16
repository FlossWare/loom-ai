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

A caller-supplied execution identity is unique within the durable execution
store. Submitting a new Intent with an identity that already exists MUST NOT
overwrite the existing state, replace its Result, or invoke Workers again. The
Orchestrator MUST return an explicit machine-readable identity-conflict outcome
and preserve the original execution for observation. A client that times out
while submitting MUST observe the known execution identity before deciding
whether to submit new work; a transport timeout does not establish that the
original request was rejected.

A conforming Orchestrator MUST provide a cancellation operation with
semantics equivalent to `RequestCancellation(execution_id, reason?)`. The
operation name and transport representation are not normative. It MUST return
the current execution snapshot and make clear whether cancellation was accepted,
was already requested, was unsupported, or arrived after a terminal outcome.

Cancellation requests MUST be idempotent for an execution identity. A request
against an already-terminal execution MUST return its existing terminal outcome
without rewriting it. For an active execution, the Orchestrator MUST durably
record the request before reporting it as accepted and propagate cancellation to
the active work. The operation MAY return while cleanup is in progress, but the
observable state MUST distinguish a pending request from confirmed termination.
An execution MUST NOT be reported as `cancelled` until the work has stopped and
the terminal state has been persisted.

Cancellation is cooperative unless a Worker contract explicitly provides a
stronger interruption guarantee. Workers MUST check cancellation before starting
new work and at documented safe points. If a Worker cannot stop immediately, the
Orchestrator MUST expose that cancellation is still pending rather than claiming
that the work has terminated. If cancellation races with completion, the
Orchestrator MUST serialize the competing terminal transition: a terminal result
already committed MUST remain unchanged; an accepted cancellation that wins
before terminal completion MUST end in `cancelled` after cleanup. Partial results
and evidence MUST be retained.

Submit MAY accept an absolute execution deadline as execution metadata separate
from the Intent's objective. A deadline MUST identify one unambiguous instant
using an RFC 3339 timestamp with an explicit UTC offset. The absolute deadline
MUST be preserved across Worker handoff, observation, continuation, and process
restart; continuation MUST NOT silently reset or extend it.

When a deadline expires, the Orchestrator MUST stop scheduling new work and
request cancellation of active work. Once execution has stopped, the persisted
terminal status MUST be `failed` with an explicit `deadline_exceeded` cause,
unless a later version of the contract defines a dedicated terminal status with
an equivalent unambiguous mapping. Deadline expiry MUST NOT be conflated with a
user-requested cancellation. If the deadline is already expired before initial
execution or continuation begins, no new Worker invocation may start; the
Orchestrator MUST persist the deadline failure when durable state is configured.
If a Worker cannot stop promptly, the execution remains nonterminal with an
observable deadline/cancellation-pending cause until termination is confirmed.

If cancellation and deadline expiry both occur, the first termination cause
durably recorded determines the primary terminal cause. Later causes MUST remain
visible in evidence and MUST NOT overwrite the primary cause or rewrite an
already-terminal outcome.

The operations and representations are language-neutral; the contract does not
mandate method names, HTTP routes, or a particular RPC mechanism.

A production configuration that promises continuation MUST provide durable state
sufficient to reconstruct the required execution context, including the deadline
and any pending cancellation request. A non-durable transport-smoke profile MAY
exist, but MUST NOT claim restart-safe continuation.

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

Consistent with [Loom's protocol failure semantics](https://github.com/FlossWare/loom/blob/main/docs/adr/0012-protocol-failure-semantics.md),
the Orchestrator MUST distinguish a protocol failure from the Result of an
accepted Execution. A rejection before acceptance MUST NOT imply that execution
began; failures during accepted work MUST remain observable through that
Execution's lifecycle and Result. Protocol failures MUST expose a stable
machine-readable category, not only a human-readable message. Transport adapters
may translate the representation but MUST preserve the distinction and MUST NOT
disclose secrets or Evidence the caller is not authorized to access.

Recovery actions MUST follow Recovery Policy and preserve the original execution
identity, prior results, and provenance. Cancellation MUST NOT be rewritten as
ordinary failure or success. A deadline MUST NOT be silently ignored or converted
to success.

Cancellation and deadline are separate execution controls. Cancellation
records an explicit client request; deadline expiry records a system-enforced
termination cause. Both must preserve the execution identity and evidence, but
they MUST remain distinguishable in the final execution record.

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
8. transport completion is not conflated with task success;
9. cancellation requests are idempotent, pending cancellation is not reported as
   confirmed termination, and terminal-state races preserve one committed outcome;
10. deadlines survive continuation/restart, expired deadlines prevent new Worker
    invocation, and deadline expiry remains distinct from user cancellation;
11. duplicate caller-supplied execution identities produce an explicit conflict
    without overwriting prior state or invoking Workers a second time.

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
