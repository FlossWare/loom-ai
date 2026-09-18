# ADR-0013: Agent-Neutral Architecture

## Status

Accepted

## Date

2026-08-07

## Context

FlossWare provides reusable infrastructure and capabilities for AI-assisted engineering and automation. Existing and emerging agent runtimes already provide agent interaction, planning, terminal/IDE integration, session management, and user interfaces.

Building a FlossWare-specific agent runtime or UI would duplicate capabilities that are not central to FlossWare's value and would couple the platform to a particular interaction model or vendor.

FlossWare instead needs to remain useful to multiple agent runtimes, including OpenCode, Claude Code, Codex, and future implementations.

## Decision

FlossWare SHALL be agent-neutral.

- FlossWare SHALL provide capabilities and infrastructure rather than require a particular AI agent runtime.
- FlossWare SHALL NOT require a FlossWare-owned conversational UI, terminal UI, IDE, or agent shell.
- External agents MAY consume FlossWare capabilities through MCP, REST, events, or other explicitly supported contracts.
- Agent-specific behavior SHALL remain outside FlossWare capability implementations unless it is itself a reusable platform capability.
- FlossWare integrations SHALL prefer standards-based contracts over agent-specific SDK coupling.
- An agent runtime is a client of FlossWare, not a required architectural layer inside FlossWare.

## Consequences

### Positive

- Existing agent runtimes can be used without rebuilding their user experiences.
- FlossWare remains independent of model and agent vendors.
- Agent capabilities can evolve independently of agent UX.
- Multiple agents can consume the same FlossWare infrastructure.

### Negative

- FlossWare must maintain stable external contracts.
- Agent-specific features may require adapters outside the core platform.
- Integration testing must cover multiple client/runtime behaviors where interoperability matters.

## Alternatives Considered

### Build a FlossWare agent and UI
Rejected — duplicates mature agent runtimes and shifts effort away from reusable infrastructure.

### Standardize on one external agent
Rejected — creates unnecessary vendor and runtime coupling.

### Agent-neutral capability platform (chosen)
Keeps FlossWare focused on reusable infrastructure and allows external agents to compete and evolve independently.

## Related ADRs

- [ADR-0004](0008-mcp-tool-contracts.md) — MCP and Tool Contracts
- [ADR-0007](ADR-0007-unified-client-service-contract.md) — Unified Client-Service Contract
- [ADR-0009](ADR-0009-core-architecture-principles.md) — Core FlossWare Architecture Principles
- [ADR-0010](ADR-0010-rest-service-boundaries.md) — REST Service Boundaries
- [ADR-0018](0014-mcp-capability-exposure.md) — MCP Capability Exposure
