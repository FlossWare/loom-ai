# ADR-002: External Agent Execution Boundary

- **Status:** Proposed
- **Date:** 2026-09-16
- **Related:** #936, #946, #947, #948, #949, #950, #996

## Context

Loom is intended to be an execution substrate rather than a coding-agent product tied to a particular interactive client. An external agent such as Crush, another coding agent, or a future service should be able to submit meaningful work to Loom and consume the resulting evidence without knowing Loom's internal Worker, Arbiter, execution, or model-provider implementation.

Loom already has an application-boundary direction in which REST, MCP, and CLI/TUI adapters reach the Orchestrator rather than creating independent execution paths. The external-agent use case makes that boundary a hard architectural requirement rather than an integration convenience.

The immediate dogfood target is a real coding workflow: an external client submits an ordinary engineering request, Loom performs repository inspection and bounded execution, verification determines whether the work actually succeeded, and the client receives the result and evidence. The same boundary must remain suitable for future remote Loom-to-Loom execution.

## Decision

Loom will expose an **agent-neutral external execution boundary**.

External agents and clients consume Loom through public application adapters. REST is the canonical HTTP application API. MCP is an adapter over the same application-facing orchestration contract. Other adapters, including CLI/TUI, must use the same contract rather than introducing a second orchestration path.

The boundary is conceptually:

```text
External Agent / Client
          |
          v
   REST / MCP / CLI-TUI
          |
          v
   Loom application boundary
          |
          v
      Orchestrator
          |
     coordination
          v
 Worker / Arbiter composition
          |
          v
      Execution
          |
          v
 Verification + provenance
          |
          v
 Results / evidence / lifecycle state
```

An external client submits a first-class Intent/task. Loom owns correlation, lifecycle, orchestration, execution, verification, provenance, and result semantics. The client consumes those semantics but does not become an orchestration authority.

## Boundary responsibilities

### External agent/client

The client may:

- submit an Intent/task;
- provide task inputs, constraints, and requested capabilities;
- observe task/session lifecycle state;
- retrieve results and execution evidence;
- receive explicit success, failure, cancellation, timeout, and verification outcomes;
- continue work using persisted state where the public contract permits it.

The client must not:

- invoke Workers directly as workflow authorities;
- invoke Arbiter internals directly;
- bypass the Orchestrator;
- invoke `ExecutionEngine` as an external workflow authority;
- select or call model providers as part of Loom execution;
- access local-only Loom state unless explicitly exposed and authorized.

### Loom application boundary

The application boundary owns:

- authentication and authorization;
- request validation;
- Intent/task submission;
- correlation IDs and lifecycle state;
- cancellation and deadlines;
- result and failure semantics;
- provenance and execution evidence;
- access to explicitly exposed capabilities.

REST and MCP must expose the same underlying semantics. Differences between protocols are transport and presentation concerns, not differences in orchestration behavior.

### Orchestrator

The Orchestrator remains the workflow authority. It coordinates Workers, Arbiter composition, execution, verification, persistence, and failure/requeue behavior according to Loom's internal contracts.

### Workers, Arbiter, and model routing

Workers perform bounded capabilities. Arbiter coordinates or composes execution where appropriate. Model/provider selection remains behind the existing model-routing/configuration boundaries. External agents do not gain a back door into provider selection merely because they can submit work to Loom.

## Execution semantics

External execution is ordinary Loom execution, not a special "agent mode".

A representative request is:

```text
Intent
  -> admission/authentication
  -> Orchestrator
  -> Worker/Arbiter execution
  -> verification
  -> persisted result/evidence
  -> external response
```

A successful response must be grounded in the verification semantics of the requested task. If required verification fails, the external client must receive an explicit failure or continuation state rather than an assertion of success.

Execution tracing may expose structured execution evidence and concise decision rationale where appropriate. Loom does not persist or expose model private chain-of-thought. See ADR-001.

## Security and isolation

The external boundary is a capability boundary.

- Authentication identifies the calling client.
- Authorization determines which capabilities, repositories, resources, and remote operations the client may use.
- Local filesystem, process, credentials, provider configuration, and other private state remain inaccessible unless explicitly exposed through an authorized capability.
- Remote Loom integrations must preserve the same isolation guarantees across the network boundary.
- Provenance must identify the relevant execution boundary so local and remote work are distinguishable.

## Remote Loom compatibility

The design intentionally permits a Loom instance to consume another Loom instance through the same application-level concepts. Remote Loom-to-Loom execution is not a separate internal architecture. It is an external capability boundary with explicit authentication, authorization, correlation, provenance, and failure semantics.

This permits a local Loom to remain the control plane while selected capabilities are delegated to a remote Loom instance without sharing local files, processes, or internal configuration.

## Alternatives considered

### Agent-specific integration inside Loom

Rejected. It couples Loom to one client and encourages special-case execution paths. Crush is a dogfood client, not an architectural dependency.

### Direct Worker access from external agents

Rejected. It bypasses orchestration, weakens verification and provenance guarantees, and makes the public contract depend on internal implementation details.

### MCP as Loom's internal architecture

Rejected. MCP is an adapter/protocol boundary, not Loom's internal orchestration model. Loom must remain usable through REST and other application adapters without making MCP a prerequisite for internal execution.

### Model-provider API exposed to the external agent

Rejected. Model/provider selection belongs behind Loom's routing/configuration boundaries. The external agent requests work; it does not become Loom's provider-routing authority.

## Consequences

### Positive

- Loom remains agent-neutral and reusable.
- Crush can become a real Loom-backed coding client without defining Loom around Crush.
- REST and MCP can be tested against the same application contract.
- Verification, provenance, and failure semantics remain centralized.
- Remote Loom-to-Loom execution has a natural architectural home.
- Future clients can integrate without learning Loom internals.

### Negative

- The application boundary must become sufficiently complete to support real engineering workflows.
- Authentication and authorization become first-class engineering concerns.
- Lifecycle, result, provenance, and verification schemas must be stable enough for external consumers.
- Dogfooding will expose missing capabilities that must be implemented as focused Loom work rather than hidden in client-specific glue.

## Implementation direction

The architectural decision is implemented incrementally through existing focused work:

1. Complete the REST Orchestrator application boundary (#936).
2. Keep first-class Intent definitions and correlation (#947).
3. Keep Arbiter/Worker composition behind the same execution contract (#948).
4. Dogfood a real external coding client through Loom (#949).
5. Support authenticated remote Loom capabilities without changing the internal orchestration model (#950).
6. Preserve structured execution evidence while excluding private chain-of-thought (#946, ADR-001).

The external-agent dogfood is the acceptance path: a fresh client session must be able to submit a real repository task, inspect the repository through Loom capabilities, make a real change, execute verification, and receive verifiable evidence of the outcome.

## Status

Proposed pending review and merge. Implementation work should proceed through focused issues linked to this ADR; the ADR itself should not become a substitute for executable tests or implementation tracking.
