# ADR-0001: Portable Learning Artifacts and Shared Learning

- **Status:** Accepted
- **Date:** 2026-10-03
- **Decision:** Learning artifacts are portable, versioned domain artifacts independent of the runtime that produced them.

## Context

Claude Ensemble (CE) is being used as a lightweight neural/learning laboratory. Its purpose is to experiment with learning techniques and provide empirical evidence about which techniques are worth promoting into Loom.

That creates a boundary problem: a useful CE experiment is of limited architectural value if its learned state, experience, or evidence is trapped inside CE's implementation.

Loom already treats Knowledge as a shareable domain concern. Learning should follow the same architectural principle without making CE a dependency of Loom.

## Decision

Loom treats reusable learning artifacts as provider-neutral, language-neutral, versioned domain artifacts.

A learning artifact MAY represent:

- a teaching signal;
- an execution outcome or feedback signal;
- a learned experience;
- an embedding and its provenance;
- learned routing or calibration state;
- an experiment dataset or result;
- a learned optimization strategy state.

The artifact contract describes semantics and provenance, not the algorithm or implementation that produced the artifact.

Learning artifacts MUST be separable from:

- execution/runtime state;
- provider SDKs and credentials;
- private prompts and secrets;
- proprietary source material unless explicitly authorized for sharing;
- private reasoning traces.

An artifact SHOULD contain enough provenance and version information to support independent inspection, evaluation, replay, and controlled promotion.

## Rationale

This allows CE to act as a genuine experimental laboratory:

```text
CE experiment
    |
    v
portable learning artifact
    |
    +--> evaluate
    |
    +--> share
    |
    +--> reproduce/replay
    |
    v
Loom promotion candidate
```

A successful technique can therefore be promoted into Loom without importing CE's storage layout, Python implementation, or orchestration model.

A failed technique can be discarded while retaining its experimental evidence.

## Consequences

### Positive

- CE experiments produce reusable evidence rather than CE-specific state.
- Loom can consume learning produced elsewhere.
- Learning can be shared between compatible systems in the same way Knowledge can be shared.
- Learned state gains explicit provenance and versioning.
- Experiments can be evaluated offline before becoming production behavior.
- Loom remains independent of any particular neural algorithm.

### Negative

- We must define and maintain stable learning-artifact semantics.
- Not every learned artifact will be portable, especially model-specific weights or private data.
- Provenance and compatibility become part of the artifact lifecycle.
- Sharing learned state requires explicit data-boundary and privacy controls.

## Non-goals

This ADR does not:

- require a neural network or any particular learning algorithm;
- require model weights to be portable;
- define the final learning-artifact schema;
- create a generalized learning framework;
- make CE a Loom runtime dependency;
- replace the Execution Outcome and Feedback Contract;
- permit learned optimization to bypass policy, authorization, safety, or budget constraints.

## Relationship to existing architecture

The decision extends the existing language-neutral AI-domain boundary. It does not change the semantics of Intent, Worker, Arbiter, Result, or Evidence.

Execution outcomes and feedback remain governed by the outcome/feedback contract. Learning artifacts are the portable representations that may be produced from those outcomes and used by learning or optimization strategies.

Adaptive routing and optimization strategies may consume learning artifacts, but the artifact contract does not prescribe Thompson Sampling, contextual bandits, genetic algorithms, neural networks, or any other technique.

## Promotion rule

A CE learning experiment should be considered for Loom promotion only when its results demonstrate measurable value for a defined workload.

The default lifecycle is:

1. Experiment in CE.
2. Emit portable artifacts and measurements.
3. Evaluate reproducibility, value, cost, and operational implications.
4. Promote the technique and contract into Loom only when evidence justifies it.
5. Otherwise retain the experiment as research evidence and do not burden Loom with it.

Related: CE #175; Loom #1019, #964, #967.
