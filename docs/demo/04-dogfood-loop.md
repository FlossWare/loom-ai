# Dogfood Loop

Once the demo works, Loom becomes the first consumer of its own engineering memory.

## Loop

```text
             ┌──────────────────┐
             │  Give Loom task  │
             └────────┬─────────┘
                      ↓
             investigate/implement
                      ↓
                   test
                      ↓
             record knowledge
                      ↓
             end session
                      ↓
             new Loom session
                      ↓
             retrieve knowledge
                      ↓
             continue development
                      │
                      └──────────────→ repeat
```

## Operating principle

Do not ask whether Loom can theoretically support a feature before dogfooding it when a smaller real-world experiment can answer the question.

When Loom fails:

1. preserve the failure as evidence
2. determine whether the failure is implementation, contract, memory, retrieval, model, or tooling related
3. create/update a focused issue
4. implement the smallest architectural improvement that addresses the failure
5. use Loom to verify the improvement

## Examples

### Context failure

If Loom forgets why a previous change was made:

- inspect what was persisted
- inspect retrieval
- improve canonical memory/context behavior
- rerun the two-session demonstration

### Graph failure

If Loom retrieves semantically similar information but misses an important relationship:

- capture the query and missing relationship
- evaluate graph retrieval
- improve the canonical graph model/retrieval path
- rerun the scenario

### Concurrent-session failure

If two Loom sessions overwrite or misunderstand shared knowledge:

- preserve both session identities and events
- identify the conflicting state
- improve shared-state semantics
- add a regression test

### External-AI failure

When Claude, Cursor, Crush, OpenCode, or another agent produces useful information that Loom cannot ingest:

- preserve the source/provenance
- add or improve the appropriate ingestion adapter
- make the resulting knowledge available to Loom and future agents

## Strategic outcome

The purpose of dogfooding is not merely to prove that Loom works. It is to make Loom's own development process the workload that drives its architecture.
