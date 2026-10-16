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

## Reusable artifacts and experiment telemetry

Experiment telemetry and portable learning artifacts are related but distinct:

- **Experiment telemetry** records observations about a run, such as timing, cost, intermediate measurements, debug events, and experiment-specific operational details. Telemetry MAY be retained as research evidence, but it is not automatically reusable learned state.
- **A portable learning artifact** is an explicitly identified, versioned domain object with declared semantics, provenance, intended use, and relevant compatibility and data-boundary information.

Raw telemetry MUST NOT be treated as a portable learning artifact merely because it was produced by a learning experiment. A dataset, measurement, or outcome MAY be promoted into an artifact when its meaning and intended use are explicit and its privacy and sharing constraints are satisfied. Telemetry needed to reproduce or evaluate an artifact may accompany it as separate evidence without becoming part of the artifact's learned state.

This distinction lets systems retain detailed experimental evidence without coupling consumers to a particular experiment runner or mistaking logs for reusable policy, experience, or calibration.

## Rationale

This allows CE to act as a genuine experimental laboratory:

```text
CE experiment
    |
    +--> experiment telemetry (research evidence)
    |
    v
explicitly selected learning artifact
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
- Experiment telemetry remains available for research without being confused with portable learned state.

### Negative

- We must define and maintain stable learning-artifact semantics.
- Not every learned artifact will be portable, especially model-specific weights or private data.
- Provenance and compatibility become part of the artifact lifecycle.
- Sharing learned state requires explicit data-boundary and privacy controls.
- Artifact promotion requires explicit classification and validation rather than indiscriminate copying of experiment output.

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
2. Retain experiment telemetry and measurements as research evidence.
3. Explicitly classify and emit portable learning artifacts with provenance and version identity.
4. Evaluate reproducibility, value, cost, privacy, and operational implications.
5. Promote the technique and contract into Loom only when evidence justifies it.
6. Otherwise retain the experiment as research evidence and do not burden Loom with it.

Related: CE #175; Loom #1019, #964, #967.
