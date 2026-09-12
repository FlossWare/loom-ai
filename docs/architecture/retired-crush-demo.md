# Retired Crush Demo

`FlossWare/crush-demo` was a thin Fedora integration and dogfood repository for the former `agent-setup` / `agent-ai` architecture.

Its useful purpose was demonstrating an end-to-end Crush integration. That responsibility now belongs to the canonical Loom client and setup boundaries:

```text
Crush
  -> loom-client-setup
  -> Loom interface / MCP
  -> loom-ai
  -> Workers / Arbiters
  -> model-gateway and capabilities
```

## What was preserved

- Crush remains a supported external Loom client.
- Crush integration guidance moved to `loom-client-setup/docs/crush-integration.md`.
- Loom itself remains the dogfood target. A separate demo repository is not required to prove the runtime.
- The historical repository remains useful only as archaeology until GitHub repository archiving is performed.

## What was not preserved

The old installer and architecture are intentionally not carried forward. They depended on `agent-setup`, `flossware-ai`, and the former agent runtime, all of which have been superseded by Loom's current boundaries.

## Decision

Do not add new implementation work to `crush-demo`. Archive it after confirming the preserved Crush integration documentation is sufficient.
