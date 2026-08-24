# FlossWare AI Architecture

Loom AI is the complete external orchestration platform. It is not a required runtime dependency for individual FlossWare AI libraries.

## Three layers

1. **Composable libraries**: routing, resilience, structured output, consensus, evaluation, observability, security, RAG, optimization, search, and vector capabilities remain independently importable and serviceable.
2. **Agent/control-plane tooling**: `coding-agent-setup` provides shared profiles, account/model discovery, credential references, MCP adapters, CLI, and TUI configuration for Claude Code, Crush, Codex, OpenCode, Cursor, and other supported agents.
3. **Loom AI**: composes the capabilities into the full external platform and exposes headless APIs plus optional CLI/TUI surfaces.

## TUI boundary

Loom core has no curses dependency. `loom-tui` is an optional presentation layer using `FlossWare/curses-themes`.

The agent setup TUI is separate. It configures individual capabilities for whichever coding agent is being used. Both surfaces consume shared configuration conventions but neither embeds the other.

## Credential boundary

Credentials belong to provider/native credential stores or environment/secret managers. Generated agent files and manifests contain credential-source metadata only. Loom and individual libraries may resolve credentials through their own provider contracts.

## Composition

```text
Claude / Crush / Codex / OpenCode
          |
          v
FlossWare agent adapters + MCP
          |
          +---- individual component ----> model-router / RAG / search / ...
          |
          +---- complete platform -----> Loom AI
                                            |
                                            +--> all FlossWare capabilities
```

This makes Loom the meat-and-potatoes platform without turning the underlying FlossWare ecosystem into a monolith.
