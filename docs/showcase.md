# Showcase: the engineer that remembers

An inspirational narrative demo of Loom’s differentiator — not another chatbot, but an **orchestration substrate that outlives the chat**.

## Run offline (zero keys)

```bash
python examples/showcase_demo.py
```

## Run with live free models

```bash
export LOOM_LLM_BASE_URL=https://openrouter.ai/api/v1
export LOOM_LLM_API_KEY=sk-or-v1-YOUR_KEY
export LOOM_LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
# Optional multi-model council:
export LOOM_SHOWCASE_MODELS=meta-llama/llama-3.3-70b-instruct:free,google/gemma-2-9b-it:free
python examples/showcase_demo.py
```

## Optional real storage

```bash
export LOOM_STORAGE=postgresql   # plus LOOM_PG_*
python examples/showcase_demo.py
```

Decisions are always written to a durable vault file (survives process kill). When LoomConfig is available they are also stored via `storage.store_document`.

## Story arc

| Act | What you see |
|-----|----------------|
| **I · The Council** | Multi-model consensus (live or offline) |
| **II · Ink Into Stone** | Decisions with provenance + Loom storage |
| **III · The Lights Go Out** | Process death |
| **IV · Cold Start** | Recovery without the prior transcript |
| **V · The Open Door** | Keyless `/v1` free gateway |

Maps to epic #681: execute → persist → die → recover → open edge.

## Gateway

```bash
python -m loom_ai.server_demo
```

See [public-free-gateway.md](public-free-gateway.md).
