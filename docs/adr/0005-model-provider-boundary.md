# ADR 0005: Provider-neutral model boundary

- Status: Accepted
- Date: 2026-09-16
- Tracking: #954

## Context

Loom Workers need model-backed capabilities without becoming coupled to a
specific model vendor, credential scheme, gateway, routing strategy, or model
SDK. Loom also needs a stable seam that can later be implemented in another
language, including Java.

## Decision

Loom defines a minimal provider-neutral capability:

```text
ModelProvider.generate(ModelRequest) -> ModelResponse
```

`ModelRequest` contains only the prompt, requested model identifier, and
non-secret metadata. `ModelResponse` contains generated text, provider/model
provenance, a finish reason, and non-secret metadata.

A `ModelWorker` adapts a Loom `Intent` to this contract. It knows the
provider-neutral interface, not provider or vendor mechanics.

A deterministic fake provider is the reference implementation for tests and
Stage 5 dogfood.

## Boundaries

The following remain outside Loom core:

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
provider infrastructure can evolve behind the seam without expanding the Loom
execution model.
