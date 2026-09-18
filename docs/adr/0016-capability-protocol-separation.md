# ADR-0016: Capability and Protocol Separation

## Status

Accepted

## Date

2026-08-07

## Context

FlossWare capabilities may be consumed through MCP, REST/OpenAPI, asynchronous events, internal APIs, or other protocols. Treating a protocol as the capability itself causes duplicated business logic, inconsistent behavior, and unnecessary coupling.

FlossWare needs a stable architectural model in which the reusable capability remains independent of how it is exposed.

## Decision

FlossWare SHALL separate capability implementation from protocol exposure.

A capability is the reusable unit of business or infrastructure behavior. A protocol adapter translates a consumer-specific contract into that capability.

```text
                  Capability
                      |
          +-----------+-----------+
          |           |           |
         MCP        REST        Event
          |           |           |
       Agents     Clients      Services
```

### Rules

- Capability implementations SHALL NOT depend on transport-specific request/session types.
- Protocol adapters SHALL contain translation and contract concerns, not duplicate business logic.
- Multiple protocols MAY expose the same capability.
- A protocol MAY expose only a subset of a capability when required by its consumer or security model.
- Authorization SHALL be enforced at the service/capability boundary and MAY be additionally enforced by protocol adapters.
- Protocol-specific concerns such as MCP tool schemas, HTTP serialization, event envelopes, and transport errors SHALL remain outside the core capability implementation.

### Database boundary

Database access is an implementation concern behind service boundaries. Stored procedures MAY provide stable database-level contracts according to [ADR-0011](ADR-0011-stored-procedure-database-access.md), but database contracts SHALL NOT become direct agent or external-client contracts.

## Consequences

### Positive

- Business logic has one implementation.
- MCP, REST, and event consumers can evolve independently.
- Protocol replacement becomes practical.
- Security and compatibility concerns remain localized.
- Testing can distinguish capability behavior from protocol behavior.

### Negative

- Adapter code and contract tests are required.
- Some capabilities need deliberate mapping between protocol semantics.

## Alternatives Considered

### Protocol-specific implementations
Rejected — duplicates behavior and causes drift.

### One universal protocol
Rejected — different consumers have different interaction and delivery requirements.

### Capability with protocol adapters (chosen)
Provides stable reusable behavior while supporting appropriate contracts for agents, clients, and services.

## Related ADRs

- [ADR-0004](0008-mcp-tool-contracts.md) — MCP and Tool Contracts
- [ADR-0005](ADR-0005-event-driven-internal-bus.md) — Event-Driven Internal Bus
- [ADR-0010](ADR-0010-rest-service-boundaries.md) — REST Service Boundaries
- [ADR-0011](ADR-0011-stored-procedure-database-access.md) — Stored Procedure Database Access
- [ADR-0017](0013-agent-neutral-architecture.md) — Agent-Neutral Architecture
- [ADR-0018](0014-mcp-capability-exposure.md) — MCP Capability Exposure
