# Loom Demo

This directory defines the first **dogfoodable Loom demonstration**.

The goal is deliberately smaller than the long-term Loom vision. We need a working vertical slice that can perform a real development task, persist useful knowledge, survive a session boundary, and then use that knowledge in a later session.

## Demo definition

> Give Loom a GitHub issue, have it investigate and implement the change, run tests, record useful discoveries and decisions, end the session, start a new session, and ask Loom to explain what happened.

The second session must recover useful context from persistent Loom state rather than relying on the original conversation transcript.

## Success criteria

- [ ] Start Loom locally.
- [ ] Connect to a model through the existing provider abstraction.
- [ ] Give Loom a concrete repository task.
- [ ] Inspect repository files.
- [ ] Use tools to modify code.
- [ ] Run relevant tests.
- [ ] Persist the session.
- [ ] Persist useful observations and decisions.
- [ ] End the process/session.
- [ ] Start a fresh session.
- [ ] Retrieve prior project/session knowledge.
- [ ] Explain the previous work and reasoning.
- [ ] Use Loom itself to make at least one follow-up change to Loom.

## What is intentionally out of scope

The demo does **not** need to complete the entire long-term architecture first.

Defer unless required by the vertical slice:

- Loom-to-Loom federation
- GraphQL as a public API
- sophisticated graph inference
- full external-AI interaction ingestion
- distributed multi-server coordination
- elaborate consensus mechanisms
- broad provider-specific integrations

These remain valuable roadmap work. The demo exists to create a working feedback loop for implementing them later.

## Dogfood principle

Once the demo works, Loom should be used to develop Loom.

Every limitation encountered while dogfooding should become evidence for the next implementation issue rather than another speculative feature.

## Documents

- `01-demo-scenario.md` - the concrete demonstration scenario
- `02-architecture.md` - the minimum architecture required
- `03-runbook.md` - operator steps for running the demo
- `04-dogfood-loop.md` - how to use Loom to improve Loom
- `05-definition-of-done.md` - release/demo acceptance criteria
