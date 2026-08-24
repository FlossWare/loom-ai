# Loom TUI

The Loom TUI is an optional presentation layer for the Loom platform. It is not part of the Loom core runtime and must never make curses a core dependency.

## Theme source

Use the shared FlossWare curses theme package, `flossware-curses-themes`, rather than defining Loom-specific colors or theme constants. This keeps the visual language consistent across FlossWare terminal applications.

The TUI should consume Loom APIs/services for state and actions. It should not import internal orchestration implementation details merely to render screens.

## Design goals

- shared FlossWare visual identity
- keyboard-first terminal workflow
- model/account/profile visibility
- routing and request status
- RAG/search/evaluation/consensus status where exposed by Loom
- clean separation between presentation and headless core
- usable over SSH and on small terminals

## Core/TUI boundary

```text
loom-ai core  <-- public API/service boundary -->  loom-ai TUI
                                                   |
                                                   +--> flossware-curses-themes
```

Installing or importing Loom core must not require curses, terminal dimensions, or a theme package.
