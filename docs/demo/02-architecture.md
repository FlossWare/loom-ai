# Demo Architecture

The demo should use the smallest existing Loom architecture that demonstrates the intended product direction.

```text
                 User
                  │
                  ▼
             Loom Client
                  │
                  ▼
             Loom Runtime
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
      Model      Tools    Context
        │         │         │
        └─────────┼─────────┘
                  ▼
          Persistent Memory
                  │
          ┌───────┴───────┐
          ▼               ▼
      Session state   Knowledge
                          │
                    provenance
```

## Required components

### Agent runtime

The runtime must be able to:

- receive a user task
- invoke the model
- select/use tools
- incorporate tool results
- continue the task loop
- stop cleanly

### Tool execution

The demo needs enough repository tooling to:

- inspect files
- search code
- inspect Git state/history
- modify files
- run tests

The exact tool implementation is less important than exercising Loom's existing contracts.

### Context

The runtime must maintain the current task context during the session and assemble a bounded context for each model turn.

### Persistent session state

The session must survive process termination. At minimum preserve:

- project/workspace identity
- session identity
- task/request
- important events or transcript references
- observations
- decisions
- verification evidence

### Knowledge

The demo does not require the complete future knowledge graph. It does require a canonical path for recording and retrieving useful engineering knowledge with provenance.

## Architectural constraint

Do not introduce a new parallel memory or graph abstraction solely for the demo.

The demo should expose gaps in the current canonical architecture and create implementation issues where necessary.

## Future expansion

The following should fit around this architecture later:

```text
             Loom Runtime
                  │
        ┌─────────┼──────────┐
        │         │          │
      Memory     Graph      MCP
        │         │          │
        └─────────┼──────────┘
                  │
              Federation
```

The demo therefore validates the foundation rather than prematurely implementing the whole roadmap.
