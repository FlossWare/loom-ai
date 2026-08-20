#!/usr/bin/env python3
"""Loom Showcase — the engineer that remembers.

An inspirational, narrative demo of what makes Loom different:

  Act I   — A council of models debates a real design question
  Act II  — Decisions are written into durable knowledge (not a chat log)
  Act III — The process dies. Completely.
  Act IV  — A fresh process wakes with no transcript — and still knows
  Act V   — The free gateway: anyone can call models with nothing Loom-shaped

Runs fully offline with stub models (zero keys, zero network).
When LOOM_LLM_BASE_URL is set, Act I can be pointed at real upstreams later.

    python examples/showcase_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

# ── terminal presence ────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"
WHITE = "\033[97m"


def c(color: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def banner(title: str) -> None:
    bar = "─" * 64
    print()
    print(c(DIM, bar))
    print(c(BOLD + CYAN, f"  {title}"))
    print(c(DIM, bar))
    print()


def beat(seconds: float = 0.35) -> None:
    """Dramatic pause (skipped when not a TTY)."""
    if sys.stdout.isatty():
        time.sleep(seconds)


def say(role: str, msg: str, color: str = WHITE) -> None:
    print(f"  {c(color + BOLD, role)}  {c(DIM, '·')}  {msg}")


# ── stub council (offline) ───────────────────────────────────────────────


class CouncilLLM:
    """Three distinct engineering voices for offline consensus."""

    _VOICES: dict[str, str] = {
        "architect": (
            "Keep the public surface OpenAI-shaped and keyless. "
            "Upstream keys stay server-side. Strip secrets and graph writes "
            "from the public mount. That is how you earn trust at the edge."
        ),
        "skeptic": (
            "Keyless public endpoints get abused. Enforce per-IP rate limits, "
            "cap max_tokens, and allowlist free models only. Without those "
            "guards the demo becomes a free proxy for someone else's bill."
        ),
        "builder": (
            "Ship a server_demo entrypoint that forces public mode, mounts /v1, "
            "and drops non-LLM routes. Document one curl and one OpenAI SDK "
            "snippet so a stranger can try it in sixty seconds."
        ),
    }

    async def chat(
        self,
        messages: list,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        from loom_ai.models import ChatResponse

        _ = messages, temperature, max_tokens
        mid = model or "architect"
        content = self._VOICES.get(
            mid, f"[{mid}] I concur with the direction of travel."
        )
        return ChatResponse(content=content, model=mid, provider="council")

    async def chat_stream(
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ) -> AsyncIterator[str]:
        resp = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        for word in resp.content.split():
            yield word + " "

    async def list_models(self) -> list[str]:
        return sorted(self._VOICES.keys())


# ── knowledge that survives process death (file-backed for the demo) ─────


@dataclass
class Decision:
    id: str
    title: str
    content: str
    provenance: list[str] = field(default_factory=list)
    session: str = ""


class DemoKnowledgeVault:
    """Minimal durable store — simulates the #681 knowledge boundary.

    Uses a single JSON file so Act III can kill the process and Act IV
    can still recall. Production path is PostgreSQL/pgvector (#684).
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._items: list[Decision] = []

    def load(self) -> None:
        import json
        from pathlib import Path

        p = Path(self._path)
        if not p.is_file():
            self._items = []
            return
        data = json.loads(p.read_text())
        self._items = [Decision(**row) for row in data]

    def save(self) -> None:
        import json
        from pathlib import Path

        Path(self._path).write_text(
            json.dumps([d.__dict__ for d in self._items], indent=2)
        )

    def remember(self, decision: Decision) -> None:
        self._items.append(decision)
        self.save()

    def recall(self, query: str) -> list[Decision]:
        q = query.lower()
        return [
            d
            for d in self._items
            if q in d.title.lower()
            or q in d.content.lower()
            or any(q in p.lower() for p in d.provenance)
        ]

    def all(self) -> list[Decision]:
        return list(self._items)


# ── Acts ─────────────────────────────────────────────────────────────────


async def act_i_council() -> list[tuple[str, str]]:
    """Multi-model consensus on the free-gateway design."""
    from loom_ai.consensus import ConsensusEngine
    from loom_ai.models import ChatMessage

    banner("ACT I  ·  The Council")
    say("Narrator", "Three models. One question. No single voice owns the truth.", DIM)
    beat()

    prompt = (
        "How should Loom expose free-tier models publicly without tying "
        "callers to Loom accounts, keys, or branding?"
    )
    say("Question", prompt, YELLOW)
    beat()

    llm = CouncilLLM()
    engine = ConsensusEngine(llm)
    voices = ["architect", "skeptic", "builder"]
    messages = [ChatMessage(role="user", content=prompt)]

    responses, failed = await engine.gather(messages, models=voices)

    collected: list[tuple[str, str]] = []
    for resp in responses:
        say(resp.model.upper(), resp.content, MAGENTA)
        collected.append((resp.model, resp.content))
        beat(0.25)

    if failed:
        say("Council", f"Silent voices: {failed}", RED)

    result = await engine.synthesize(
        prompt,
        models=voices,
        arbiter_model="architect",
        tool_name="design",
    )
    beat()
    say("Synthesis", result.synthesis.content, GREEN + BOLD)
    collected.append(("synthesis", result.synthesis.content))
    return collected


async def act_ii_write_memory(
    vault: DemoKnowledgeVault, council: list[tuple[str, str]]
) -> None:
    banner("ACT II  ·  Ink Into Stone")
    say(
        "Narrator",
        "Chat logs evaporate. Loom writes decisions with provenance.",
        DIM,
    )
    beat()

    for i, (model, content) in enumerate(council):
        d = Decision(
            id=f"dec-{i+1:02d}",
            title=f"Council voice: {model}",
            content=content,
            provenance=[f"session-1/{model}", "consensus.gather"],
            session="session-1",
        )
        vault.remember(d)
        say("Vault", f"Stored {d.id} ← {model}", CYAN)
        beat(0.15)

    say("Vault", f"{len(vault.all())} decisions durable on disk", GREEN)


def act_iii_death() -> None:
    banner("ACT III  ·  The Lights Go Out")
    say("Narrator", "Process terminated. RAM cleared. No transcript remains.", DIM)
    beat(0.5)
    say("System", "SIGTERM  ·  loom process 0", RED)
    beat(0.4)
    say("System", "… silence …", DIM)
    beat(0.6)


async def act_iv_rebirth(vault_path: str) -> None:
    banner("ACT IV  ·  Cold Start")
    say(
        "Narrator",
        "A new process. Empty context window. Only the vault remains.",
        DIM,
    )
    beat()

    vault = DemoKnowledgeVault(vault_path)
    vault.load()
    say("Process", f"pid fresh · vault entries: {len(vault.all())}", CYAN)
    beat()

    query = "rate limit"
    hits = vault.recall(query)
    say("Retrieval", f"query={query!r} → {len(hits)} hit(s)", YELLOW)
    for h in hits:
        say(
            "Provenance",
            f"{h.id}  {c(DIM, '←')}  {', '.join(h.provenance)}",
            GREEN,
        )
        say("Recall", h.content[:100] + ("…" if len(h.content) > 100 else ""), WHITE)
        beat(0.2)

    say(
        "Engineer",
        "I never saw Session 1's chat — but I know what the council decided.",
        GREEN + BOLD,
    )


def act_v_gateway() -> None:
    banner("ACT V  ·  The Open Door")
    say(
        "Narrator",
        "Callers need nothing Loom-shaped. Just an OpenAI-compatible URL.",
        DIM,
    )
    beat()
    print(
        c(
            CYAN,
            """
  # anyone, anywhere — no Loom key
  curl $GATEWAY/v1/models

  curl $GATEWAY/v1/chat/completions \\
    -H 'Content-Type: application/json' \\
    -d '{"model":"…:free","messages":[{"role":"user","content":"Hello"}]}'

  # or any OpenAI SDK
  OpenAI(base_url="$GATEWAY/v1", api_key="not-needed")
""",
        )
    )
    say(
        "Loom",
        "Upstream keys stay server-side. The public surface stays brand-neutral.",
        GREEN,
    )
    say(
        "Launch",
        "python -m loom_ai.server_demo",
        YELLOW + BOLD,
    )


async def main() -> None:
    print()
    print(c(BOLD + WHITE, "  LOOM"))
    print(c(DIM, "  the engineer that remembers"))
    print()
    beat(0.4)

    vault_path = os.environ.get(
        "LOOM_SHOWCASE_VAULT", "/tmp/loom-showcase-vault.json"
    )
    if os.path.isfile(vault_path) and os.environ.get("LOOM_SHOWCASE_KEEP") != "1":
        os.remove(vault_path)

    vault = DemoKnowledgeVault(vault_path)
    council = await act_i_council()
    await act_ii_write_memory(vault, council)
    act_iii_death()
    await act_iv_rebirth(vault_path)
    act_v_gateway()

    banner("Curtain")
    say(
        "Narrator",
        "Consensus → durable knowledge → process death → recovery → open gateway.",
        DIM,
    )
    say(
        "Narrator",
        "That is the demo. Not a chatbot. An orchestration substrate that outlives the chat.",
        GREEN + BOLD,
    )
    print()


if __name__ == "__main__":
    asyncio.run(main())
