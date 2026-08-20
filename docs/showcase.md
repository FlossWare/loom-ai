# Showcase: the engineer that remembers

An inspirational narrative demo of Loom’s differentiator — not another chatbot, but an **orchestration substrate that outlives the chat**.

## Run (zero keys, offline)

```bash
python examples/showcase_demo.py
```

## Story arc

| Act | What you see |
|-----|----------------|
| **I · The Council** | Multi-model consensus — three voices, one synthesis |
| **II · Ink Into Stone** | Decisions written with **provenance** (not a chat dump) |
| **III · The Lights Go Out** | Process death — RAM and transcript gone |
| **IV · Cold Start** | Fresh process recovers knowledge and cites sources |
| **V · The Open Door** | Keyless OpenAI-compatible free gateway |

## Why this matters

Most demos show a model answering a question. This one shows:

1. **Plurality** — more than one model, with synthesis
2. **Memory with provenance** — durable decisions, not scrollback
3. **Session boundary** — knowledge survives process kill
4. **Open edge** — strangers call free models without Loom branding

That maps directly to epic #681 (dogfoodable demo): execute → persist → die → recover → continue.

## Live free gateway

```bash
python -m loom_ai.server_demo
# curl localhost:8080/v1/models
```

See also [public-free-gateway.md](public-free-gateway.md).
