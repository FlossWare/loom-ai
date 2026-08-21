#!/usr/bin/env python3
"""Loom Showcase — the engineer that remembers (leveled up).

  Act I   — Council of models (live free upstreams when LOOM_LLM_* set)
  Act II  — Decisions into Loom storage + durable vault with provenance
  Act III — Process death
  Act IV  — Cold start: reload vault / storage, retrieve with provenance
  Act V   — Keyless free gateway

Modes
-----
Offline (default)::

    python examples/showcase_demo.py

Live free models::

    export LOOM_LLM_BASE_URL=https://openrouter.ai/api/v1
    export LOOM_LLM_API_KEY=sk-or-v1-...
    export LOOM_SHOWCASE_MODELS=model-a,model-b,model-c   # optional
    python examples/showcase_demo.py

Optional Postgres (true durability across machines)::

    export LOOM_STORAGE=postgresql
    # plus LOOM_PG_* as usual
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
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
    if sys.stdout.isatty():
        time.sleep(seconds)


def say(role: str, msg: str, color: str = WHITE) -> None:
    print(f"  {c(color + BOLD, role)}  {c(DIM, '·')}  {msg}")


class CouncilLLM:
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

    async def chat(  # NOSONAR — sync mock of async protocol
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ):
        from loom_ai.models import ChatResponse

        _ = messages, temperature, max_tokens
        mid = model or "architect"
        content = self._VOICES.get(mid, f"[{mid}] I concur.")
        return ChatResponse(content=content, model=mid, provider="council")

    async def chat_stream(
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ) -> AsyncIterator[str]:
        resp = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        for word in resp.content.split():
            yield word + " "

    async def list_models(self) -> list[str]:  # NOSONAR — sync mock of async protocol
        return sorted(self._VOICES.keys())


def _build_llm() -> tuple[Any, list[str], str]:
    """Return (llm, model_ids, mode_label)."""
    base = os.environ.get("LOOM_LLM_BASE_URL", "").strip()
    if not base:
        return CouncilLLM(), ["architect", "skeptic", "builder"], "offline council"

    from loom_ai.backends.http_llm import HttpLLMBackend

    llm = HttpLLMBackend(
        base_url=base,
        api_key=os.environ.get("LOOM_LLM_API_KEY", ""),
        default_model=os.environ.get("LOOM_LLM_MODEL", "gpt-4o-mini"),
        provider_name=os.environ.get("LOOM_LLM_PROVIDER", "free-upstream"),
    )
    raw = os.environ.get("LOOM_SHOWCASE_MODELS", "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        default = os.environ.get("LOOM_LLM_MODEL", "gpt-4o-mini")
        models = [default]
    return llm, models, f"live · {base}"


@dataclass
class Decision:
    id: str
    title: str
    content: str
    provenance: list[str] = field(default_factory=list)
    session: str = ""


class DemoKnowledgeVault:
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
        self._items = [Decision(**row) for row in json.loads(p.read_text())]

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


async def _store_in_loom(config, decision: Decision) -> None:
    if config is None:
        return
    from loom_ai.models import Document

    doc = Document(
        id=decision.id,
        title=decision.title,
        content=decision.content,
        category="decision",
        metadata={
            "provenance": decision.provenance,
            "session": decision.session,
            "kind": "showcase-decision",
        },
    )
    await config.storage.store_document(doc)


async def act_i_council(llm, models: list[str], mode: str) -> list[tuple[str, str]]:
    from loom_ai.consensus import ConsensusEngine
    from loom_ai.models import ChatMessage

    banner("ACT I  ·  The Council")
    say("Narrator", "Plurality first. No single model owns the truth.", DIM)
    say("Backend", mode, CYAN)
    beat()

    prompt = (
        "In 2-3 sentences: how should an orchestration layer expose free-tier "
        "LLM APIs publicly without requiring caller accounts or branding from "
        "the orchestrator itself?"
    )
    say("Question", prompt, YELLOW)
    beat()

    engine = ConsensusEngine(llm)
    messages = [ChatMessage(role="user", content=prompt)]
    gather_models = models if len(models) > 1 else models * 3
    responses, failed = await engine.gather(
        messages, models=gather_models[:3], temperature=0.4
    )

    collected: list[tuple[str, str]] = []
    for resp in responses:
        text = (resp.content or "").strip().replace("\n", " ")
        if len(text) > 220:
            text = text[:217] + "…"
        say((resp.model or "model").upper()[:24], text or "(empty)", MAGENTA)
        collected.append((resp.model or "model", resp.content or ""))
        beat(0.2)

    if failed:
        say("Council", f"Silent: {failed}", RED)

    arbiter = models[0]
    result = await engine.synthesize(
        prompt,
        models=gather_models[:3],
        arbiter_model=arbiter,
        tool_name="design",
        temperature=0.4,
        arbiter_temperature=0.2,
    )
    synth = (result.synthesis.content or "").strip().replace("\n", " ")
    if len(synth) > 260:
        synth = synth[:257] + "…"
    beat()
    say("Synthesis", synth, GREEN + BOLD)
    collected.append(("synthesis", result.synthesis.content or ""))
    return collected


async def act_ii_write_memory(vault, council, config) -> None:
    banner("ACT II  ·  Ink Into Stone")
    say("Narrator", "Chat logs evaporate. Decisions keep provenance.", DIM)
    beat()

    for i, (model, content) in enumerate(council):
        d = Decision(
            id=f"dec-{uuid.uuid4().hex[:8]}",
            title=f"Council voice: {model}",
            content=content,
            provenance=[f"session-1/{model}", "consensus"],
            session="session-1",
        )
        vault.remember(d)
        await _store_in_loom(config, d)
        say("Vault", f"{d.id} ← {model}", CYAN)
        beat(0.12)

    backend = type(config.storage).__name__ if config else "file-only"
    say("Vault", f"{len(vault.all())} decisions · storage={backend}", GREEN)


def act_iii_death() -> None:
    banner("ACT III  ·  The Lights Go Out")
    say("Narrator", "Process terminated. RAM cleared. No transcript remains.", DIM)
    beat(0.45)
    say("System", "SIGTERM  ·  loom process", RED)
    beat(0.35)
    say("System", "… silence …", DIM)
    beat(0.5)


async def act_iv_rebirth(vault_path: str) -> None:  # NOSONAR — called from async main
    banner("ACT IV  ·  Cold Start")
    say("Narrator", "New process. Empty context. Only durable knowledge remains.", DIM)
    beat()

    vault = DemoKnowledgeVault(vault_path)
    vault.load()
    say("Process", f"fresh pid · vault entries: {len(vault.all())}", CYAN)
    beat()

    query = "rate"
    hits = vault.recall(query)
    if not hits:
        hits = vault.recall("key")
    if not hits:
        hits = vault.all()[:1]

    say("Retrieval", f"query → {len(hits)} hit(s)", YELLOW)
    for h in hits[:3]:
        say("Provenance", f"{h.id} ← {', '.join(h.provenance)}", GREEN)
        body = h.content[:120] + ("…" if len(h.content) > 120 else "")
        say("Recall", body.replace("\n", " "), WHITE)
        beat(0.15)

    say(
        "Engineer",
        "I never saw Session 1's chat — but I know what the council decided.",
        GREEN + BOLD,
    )


def act_v_gateway() -> None:
    banner("ACT V  ·  The Open Door")
    say("Narrator", "Nothing Loom-shaped for callers. OpenAI-compatible only.", DIM)
    beat()
    print(
        c(
            CYAN,
            """
  curl $GATEWAY/v1/models
  curl $GATEWAY/v1/chat/completions -H 'Content-Type: application/json' \\
    -d '{\"model\":\"…:free\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'
  OpenAI(base_url=\"$GATEWAY/v1\", api_key=\"not-needed\")
""",
        )
    )
    say("Launch", "python -m loom_ai.server_demo", YELLOW + BOLD)


async def main() -> None:
    print()
    print(c(BOLD + WHITE, "  LOOM"))
    print(c(DIM, "  the engineer that remembers"))
    print()
    beat(0.3)

    vault_path = os.environ.get(
        "LOOM_SHOWCASE_VAULT",
        os.path.join(tempfile.gettempdir(), "loom-showcase-vault.json"),
    )
    if os.path.isfile(vault_path) and os.environ.get("LOOM_SHOWCASE_KEEP") != "1":
        os.remove(vault_path)

    llm, models, mode = _build_llm()
    config = None
    try:
        from loom_ai.config import LoomConfig

        config = await LoomConfig.from_env()
        say("Config", f"storage={type(config.storage).__name__}", DIM)
    except Exception as exc:
        say("Config", f"LoomConfig skipped: {type(exc).__name__}", DIM)

    vault = DemoKnowledgeVault(vault_path)
    council = await act_i_council(llm, models, mode)
    await act_ii_write_memory(vault, council, config)
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
        "Not a chatbot. An orchestration substrate that outlives the chat.",
        GREEN + BOLD,
    )
    print()


if __name__ == "__main__":
    asyncio.run(main())
