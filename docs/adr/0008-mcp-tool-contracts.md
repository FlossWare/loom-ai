# ADR-0008: MCP and Tool Contracts

> Formerly `docs/architecture/decisions/ADR-0003-mcp-tool-contracts.md`

## Status
Accepted

## Date
2026-08-07

## Context

AI agents need predictable discovery and invocation of capabilities across repositories, infrastructure, and services. Ad-hoc tool wiring per agent creates fragile integrations and unclear security boundaries.

FlossWare is intentionally agent-neutral. Existing agent runtimes such as OpenCode, Claude Code, Codex, and future runtimes are clients of FlossWare rather than components FlossWare must implement or replace.

## Decision

Tools SHALL expose explicit contracts.

- MCP-compatible interfaces SHOULD be preferred for **AI-agent** capability discovery and invocation.
- MCP SHALL be treated as a protocol adapter over reusable FlossWare capabilities, not as a business-logic layer ([ADR-0018](0014-mcp-capability-exposure.md), [ADR-0020](0016-capability-protocol-separation.md)).
- MCP is **not** a replacement for REST/OpenAPI (external synchronous service contracts) or for asynchronous internal events.
- The same underlying capability MAY be exposed through both MCP and REST/OpenAPI when appropriate.
- MCP exposure SHALL be independently enabled through explicit configuration and SHALL NOT activate merely because an MCP dependency or server is present ([ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md)).
- MCP tools SHALL have explicit schemas, error semantics, side-effect classification, and authorization requirements ([ADR-0019](0015-agent-tool-security-and-authorization.md)).

### Layered model

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

**Read order for this cluster:** [ADR-0020](0016-capability-protocol-separation.md) → this ADR → [ADR-0018](0014-mcp-capability-exposure.md) → [ADR-0019](0015-agent-tool-security-and-authorization.md) → [ADR-0017](0013-agent-neutral-architecture.md).

## Consequences

### Positive
- Agents consume capabilities instead of implementations.
- Integrations become replaceable and agent-neutral.
- Security boundaries become explicit at the tool/capability surface.
- One capability can serve agents, applications, and asynchronous consumers.

### Negative
- Dual contract maintenance may be required when a capability is exposed through multiple protocols.
- MCP ecosystem maturity varies by language/runtime.
- MCP authorization and contract testing add operational work.

## Alternatives Considered

### OpenAPI-only for agents
Rejected as the sole agent contract — weaker standardized agent-oriented discovery and invocation than MCP for agent runtimes.

### Custom JSON-RPC / proprietary tool protocol
Rejected — higher integration cost and weaker ecosystem leverage.

### gRPC reflection as primary agent contract
Rejected for agent-facing tools — less agent-ecosystem alignment than MCP; still valid for internal service meshes.

### MCP for agents + REST for services + events for asynchronous integration (chosen)
Matches consumer needs without forcing one protocol everywhere.

## Related ADRs
- [ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md) — Explicit Opt-In Cross-Cutting Infrastructure Behavior
- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0005](ADR-0005-event-driven-internal-bus.md) — Event-Driven Internal Bus
- [ADR-0007](ADR-0007-unified-client-service-contract.md) — Unified Client-Service Contract
- [ADR-0010](ADR-0010-rest-service-boundaries.md) — REST Service Boundaries
- [ADR-0017](0013-agent-neutral-architecture.md) — Agent-Neutral Architecture
- [ADR-0018](0014-mcp-capability-exposure.md) — MCP Capability Exposure
- [ADR-0019](0015-agent-tool-security-and-authorization.md) — Agent Tool Security and Authorization
- [ADR-0020](0016-capability-protocol-separation.md) — Capability and Protocol Separation
