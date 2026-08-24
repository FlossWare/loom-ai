# Agent composability

Loom AI is the complete external FlossWare AI platform, but Loom does not own the underlying AI capabilities.

## Architecture

- **Loom core** is headless. It provides orchestration, routing, RAG, evaluation, consensus, resilience, observability, and workflow capabilities through APIs and reusable Python interfaces.
- **FlossWare AI components remain independently usable.** Coding agents and applications may consume model routing, structured output, resilience, evaluation, consensus, semantic search, vector storage, observability, and workflow capabilities without running Loom.
- **Agent adapters are a compatibility layer.** Claude Code, Crush, Codex, OpenCode, Cursor, and other clients should use the individual capabilities they need, or connect to Loom for the complete platform experience.
- **The gateway is an adapter, not a second orchestration platform.** It translates agent protocols such as OpenAI-compatible HTTP, Anthropic-compatible HTTP where supported, and MCP into calls to the selected FlossWare components or Loom. Routing, policy, RAG, evaluation, and orchestration must not be duplicated in the gateway.

## TUI

Loom core does not require a terminal UI. The supported Loom TUI is a separate presentation layer built with the shared `flossware-curses-themes` theme system. The TUI consumes Loom APIs and must remain optional so that headless deployments, services, and external agents do not depend on curses.

```text
Agents / applications
        |
        +--> individual FlossWare components
        |
        +--> agent adapters / gateway
                         |
                         +--> Loom APIs
                                 |
                 +---------------+----------------+
                 |                                |
             Loom core                       Loom TUI
             (headless)              (optional curses UI)
                 |
        FlossWare AI components
```

This is an intentional platform + composable-primitives architecture. Loom is the meat-and-potatoes platform, not a mandatory runtime dependency for every FlossWare AI component.
