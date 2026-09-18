# ADR-0014: MCP Capability Exposure

## Status

Accepted

## Date

2026-08-07

## Context

AI agents need standardized discovery and invocation of FlossWare capabilities. ADR-0004 establishes MCP as the preferred agent-facing tool contract, but the architecture also needs to define where MCP belongs relative to service implementations, REST APIs, and asynchronous events.

MCP must not become a second business-logic layer. A capability should have one implementation and may have multiple protocol adapters.

## Decision

FlossWare SHALL treat MCP as an agent-facing protocol adapter over reusable capabilities.

### Capability and protocol separation

- A FlossWare capability SHALL be implemented independently of MCP, REST, or event transport concerns.
- MCP tools SHALL delegate to existing service/capability implementations rather than duplicate business logic.
- REST/OpenAPI and MCP MAY expose the same underlying capability when both consumer types are appropriate.
- Events SHALL remain the asynchronous integration mechanism and SHALL NOT be replaced by MCP for service-to-service workflows.
- MCP exposure SHALL be independently enabled through explicit configuration ([ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md), [ADR-0016](ADR-0016-configuration-as-source-of-truth.md)).

### Agent-facing contract

Capabilities intended for AI-agent discovery and invocation SHOULD expose MCP contracts where MCP semantics are appropriate.

MCP tools SHALL have:

- a stable, descriptive name
- an explicit input schema
- an explicit output schema
- documented error semantics
- declared side-effect characteristics
- an authorization requirement
- observability sufficient to identify the calling agent and operation

### Read and write capabilities

MCP capabilities SHOULD distinguish read-only operations from operations that mutate state.

Destructive or high-impact operations SHALL require explicit authorization and MAY require an additional approval mechanism according to deployment policy.

### No protocol leakage

Business services SHALL NOT depend on MCP-specific request/session objects. MCP adapters MAY translate MCP-specific concepts into the service's normal capability contract.

## Capability model

```text
                 FlossWare Capability
                         |
             +-----------+-----------+
             |           |           |
            MCP         REST       Events
             |           |           |
          AI Agents   Applications  Services
```

The capability is the architectural center. Protocols are replaceable exposure mechanisms.

## Consequences

### Positive

- One implementation can serve agents, applications, and asynchronous consumers.
- FlossWare remains independent of a specific agent runtime.
- MCP adoption does not require rebuilding business logic.
- Protocol changes remain isolated at adapters.

### Negative

- Multiple exposure contracts require contract testing.
- Tool schemas and service contracts must be kept intentionally aligned.
- Authorization and observability become mandatory parts of agent-facing design.

## Alternatives Considered

### MCP servers containing business logic
Rejected — duplicates capability implementations and couples domain logic to an agent protocol.

### REST-only agent integration
Rejected — does not provide the same standardized agent-oriented discovery and tool semantics.

### Separate implementations for REST and MCP
Rejected — creates drift and inconsistent behavior.

### Capability with protocol adapters (chosen)
Preserves separation of concerns while allowing the same reusable capability to serve different consumers.

## Related ADRs

- [ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md) — Explicit Opt-In Cross-Cutting Infrastructure Behavior
- [ADR-0004](0008-mcp-tool-contracts.md) — MCP and Tool Contracts
- [ADR-0005](ADR-0005-event-driven-internal-bus.md) — Event-Driven Internal Bus
- [ADR-0010](ADR-0010-rest-service-boundaries.md) — REST Service Boundaries
- [ADR-0011](ADR-0011-stored-procedure-database-access.md) — Stored Procedure Database Access
- [ADR-0019](0015-agent-tool-security-and-authorization.md) — Agent Tool Security and Authorization
