# Demo Definition of Done

The first Loom demo is complete when all of the following are true.

> **Policy:** Checkboxes are updated ONLY after operator-verified runs,
> not aspirational completion.  An item is checked when a human has
> witnessed it working end-to-end and recorded the evidence.

## Agent

- [ ] A user can give Loom a concrete repository task.
- [ ] Loom can inspect repository state.
- [ ] Loom can use repository tools.
- [ ] Loom can modify files.
- [ ] Loom can run relevant tests.
- [ ] Loom can recover from ordinary tool failures without losing the task.

## Session

- [ ] A session has a durable identity.
- [ ] Project/workspace association is persisted.
- [ ] Session state survives process termination.
- [ ] A new session can reference useful prior knowledge.

## Knowledge

- [ ] Important observations can be persisted.
- [ ] Important decisions can be persisted.
- [ ] Verification evidence can be persisted.
- [ ] Retrieved knowledge has provenance or a clear source reference.
- [ ] Unverified model claims are not presented as authoritative facts.

## Demonstration

- [ ] Session 1 completes a real Loom repository task.
- [ ] Session 1 records useful knowledge.
- [ ] Session 1 is terminated.
- [ ] Session 2 starts without the Session 1 transcript.
- [ ] Session 2 retrieves and explains the relevant prior knowledge.
- [ ] Session 2 can perform a follow-up task using that knowledge.

## Dogfooding

- [ ] Loom performs at least one development task on Loom itself.
- [ ] At least one limitation discovered during the demo is converted into a GitHub issue.
- [ ] At least one improvement is implemented and verified using Loom.

## Non-goals

The demo is **not** blocked on:

- federation
- GraphQL
- advanced graph inference
- complete external-AI ingestion
- distributed shared memory
- every model/provider integration

Those capabilities can be built through the dogfood loop after the first vertical slice is working.
