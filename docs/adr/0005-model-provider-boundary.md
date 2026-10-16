# ADR 0005: Provider-neutral model boundary

- Status: Accepted
- Date: 2026-09-16
- Tracking: #954

## Context

`loom-ai` Workers need model-backed capabilities without becoming coupled to a
specific model vendor, credential scheme, gateway, routing strategy, or model
SDK. The generic Loom protocol is defined separately in `FlossWare/loom`.

`loom-ai` also needs a stable seam that can later be implemented in another
language, including Java, without changing the Loom protocol.

## Decision

`loom-ai` defines an AI-oriented provider-neutral capability:

```text
ModelProvider.generate(ModelRequest) -> ModelResponse
```

The contract is intentionally synchronous. Async execution, threading, or
transport bridges belong in provider adapters and must not become part of the
AI capability contract merely to accommodate a provider implementation.

`ModelRequest` contains the prompt, requested model identifier, non-secret
metadata, and an optional positive finite `timeout_seconds` per-call transport
budget. `ModelResponse` contains generated text, provider/model provenance, a
finish reason, and non-secret metadata. Contract mappings are copied and
exposed immutably.

When `timeout_seconds` is present, a provider adapter MUST enforce it at its
transport boundary and raise a timeout failure rather than silently ignore the
budget. Adapters should use the transport's native timeout mechanism; a Loom
caller may reject an over-budget result after return, but cannot forcibly stop a
synchronous call that does not honor its timeout. This per-call timeout is not a
provider-selection strategy or aggregate retry/budget policy.

A `ModelWorker` adapts a Loom `Intent` to this AI capability. It forwards the
goal, requirements, constraints, and acceptance criteria as prompt context.
Acceptance criteria guide generation but do not delegate evaluation authority
to the provider: the evaluator/Arbiter remains responsible for deciding whether
the criteria were met. Criteria are prompt content, not a provider-specific
parameter or a new field in the provider-neutral request contract. The Worker
knows the provider-neutral interface, not provider or vendor mechanics.

Provider failures are mapped to a safe generic Worker error rather than
exposing provider exception text through Loom results. A response whose
provider provenance does not match the provider identity is also rejected.

A deterministic fake provider is the reference implementation for tests and
Stage 5 dogfood and is exported as part of the Stage 5 reference API.

## Boundaries

The following remain outside the `loom-ai` model capability:

- provider adapters and SDKs;
- credentials and secrets;
- routing and model selection strategies;
- retries and budgets;
- caching;
- Thompson sampling and genetic algorithms;
- Crush and Novita-specific mechanics;
- private model chain-of-thought.

Provider/model selection provenance may cross the boundary only as safe
identifiers and metadata. Credentials must never appear in Worker
configuration, evidence, or HTTP results.

## Consequences

Workers can be tested deterministically and providers can be replaced without
changing Worker logic. The boundary is deliberately small enough to preserve a
language-neutral contract for future implementations. More sophisticated
provider infrastructure can evolve behind the seam without expanding the
Loom protocol or making `loom-ai` the protocol definition.
