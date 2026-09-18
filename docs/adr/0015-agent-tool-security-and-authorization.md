# ADR-0015: Agent Tool Security and Authorization

## Status

Accepted

## Date

2026-08-07

## Context

FlossWare capabilities may be invoked by external AI agent runtimes through MCP. Agent tools can read information, modify repositories, trigger workflows, change infrastructure, or perform other consequential operations.

Agent access therefore cannot be equivalent to unrestricted service access. Tool discovery, authentication, authorization, auditing, and execution safety must be explicit.

## Decision

AI-agent access to FlossWare capabilities SHALL be treated as an explicit security boundary.

### Identity and authentication

- Agent requests SHALL be authenticated using the deployment's supported identity mechanism.
- An agent identity SHALL be distinguishable from the human or automation identity that authorized the agent when delegation is supported.
- Credentials SHALL NOT be embedded in MCP tool definitions or tool responses.

### Authorization

- Authentication SHALL NOT imply authorization to every MCP tool.
- Tool access SHALL be governed by explicit policy and configuration ([ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md), [ADR-0016](ADR-0016-configuration-as-source-of-truth.md)).
- Authorization SHALL be evaluated at the capability boundary and, where appropriate, again at the underlying service boundary.
- Least privilege SHALL be the default.

### Tool classification

MCP capabilities SHOULD be classified at minimum as:

- **read** — retrieves information without intentional state mutation
- **write** — creates or changes state
- **destructive** — deletes, revokes, or otherwise causes potentially irreversible effects
- **administrative** — changes security, infrastructure, policy, or access controls

Deployments SHALL be able to restrict these classes independently.

### High-impact operations

Destructive and administrative operations SHALL require explicit authorization. Deployments MAY require human approval or an equivalent policy gate before execution.

An agent SHALL NOT be able to escalate its own permissions through a tool invocation.

### Audit and observability

Agent-invoked operations SHALL produce sufficient audit information to determine, subject to applicable privacy requirements:

- agent identity
- delegated human/automation identity when applicable
- capability/tool invoked
- target resource
- authorization decision
- result and failure state
- correlation/request identifier

Sensitive credentials and secret values SHALL NOT be written to logs or audit records.

### Isolation and execution safety

Agent runtimes SHOULD be isolated from unrelated credentials, filesystems, and infrastructure. FlossWare deployments SHOULD scope credentials and network access to the minimum capability required.

Tool inputs SHALL be validated by the capability/service boundary and SHALL NOT be trusted merely because they originated from an agent runtime.

## Consequences

### Positive

- Agent automation has explicit and reviewable security boundaries.
- Read-only and mutating capabilities can be governed differently.
- High-impact operations can require stronger controls.
- Audit trails support incident investigation and operational accountability.

### Negative

- Tool authorization adds deployment and policy complexity.
- Agent integrations need identity and credential management.
- Some automation flows become less convenient when approval is required.

## Alternatives Considered

### Trust every connected agent
Rejected — an agent connection must not imply unrestricted authority.

### Authenticate only at the MCP server
Rejected — authentication without capability-level authorization is insufficient.

### Put authorization only in the agent runtime
Rejected — FlossWare must enforce its own capability boundary regardless of client behavior.

### Explicit capability authorization with least privilege (chosen)
Provides a reusable security model independent of any particular agent runtime.

## Related ADRs

- [ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md) — Explicit Opt-In Cross-Cutting Infrastructure Behavior
- [ADR-0010](ADR-0010-rest-service-boundaries.md) — REST Service Boundaries
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
- [ADR-0018](0014-mcp-capability-exposure.md) — MCP Capability Exposure
