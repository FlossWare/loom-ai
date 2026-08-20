"""In-memory learning extractor backend for loom-ai.

Implements the :class:`~loom_ai.contracts_workflow.LearningExtractor`
protocol via structural subtyping.  All state is held in plain dicts
and lists -- no external dependencies.  Data is lost on process exit.

Classes
-------
SimpleLearningExtractor -- pattern-based feedback detection, in-memory
    experience recording, key-phrase learning extraction, and strategy
    reward tracking for Thompson Sampling bandits.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from loom_ai.models import ChatMessage
from loom_ai.models_workflow import FeedbackSignal, Learning

# ── Feedback-detection patterns ──────────────────────────────────────────
#
# Each entry is (compiled regex, feedback type, base confidence).
# Patterns are tested against each message's *content* (case-insensitive).

_FEEDBACK_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    # Corrections -- strongest signal
    (re.compile(r"\byou\s+should\s+have\b", re.IGNORECASE), "correction", 0.9),
    (
        re.compile(r"\bthat'?s\s+not\s+(right|correct|what)\b", re.IGNORECASE),
        "correction",
        0.9,
    ),
    (
        re.compile(r"\bthat\s+is\s+not\s+(right|correct|what)\b", re.IGNORECASE),
        "correction",
        0.9,
    ),
    (re.compile(r"\bwhy\s+didn'?t\s+you\b", re.IGNORECASE), "correction", 0.85),
    (re.compile(r"\bwhy\s+did\s+not\s+you\b", re.IGNORECASE), "correction", 0.85),
    (re.compile(r"\binstead\s+of\b", re.IGNORECASE), "correction", 0.7),
    # Preferences
    (re.compile(r"\balways\s+\w+", re.IGNORECASE), "preference", 0.85),
    (re.compile(r"\bnever\s+\w+", re.IGNORECASE), "preference", 0.85),
    (re.compile(r"\bdon'?t\s+\w+", re.IGNORECASE), "preference", 0.8),
    (re.compile(r"\bdo\s+not\s+\w+", re.IGNORECASE), "preference", 0.8),
    (re.compile(r"\bprefer\s+\w+", re.IGNORECASE), "preference", 0.8),
    (re.compile(r"\bprefer\s+\w+\s+over\s+\w+", re.IGNORECASE), "preference", 0.9),
    (re.compile(r"\bavoid\s+\w+", re.IGNORECASE), "preference", 0.75),
    # Confirmations
    (re.compile(r"\bthat\s+worked\s+well\b", re.IGNORECASE), "confirmation", 0.8),
    (re.compile(r"\bgood\s+job\b", re.IGNORECASE), "confirmation", 0.7),
    (re.compile(r"\bperfect\b", re.IGNORECASE), "confirmation", 0.65),
    (
        re.compile(r"\bexactly\s+what\s+I\s+wanted\b", re.IGNORECASE),
        "confirmation",
        0.85,
    ),
    (
        re.compile(r"\bthat'?s\s+(great|correct|right)\b", re.IGNORECASE),
        "confirmation",
        0.75,
    ),
    (
        re.compile(r"\bthat\s+is\s+(great|correct|right)\b", re.IGNORECASE),
        "confirmation",
        0.75,
    ),
]


# ── Key-phrase extraction helper ─────────────────────────────────────────

# Matches simple "verb + object" phrases and notable noun phrases.
_KEY_PHRASE_RE = re.compile(
    r"\b(use|apply|avoid|prefer|try|implement|fix|handle|check|test|run|ensure)\s+"
    r"([\w\s]{2,30}?)(?:\.|,|;|$)",
    re.IGNORECASE,
)


def _extract_key_phrases(text: str) -> list[str]:
    """Return de-duplicated key phrases from *text*."""
    seen: set[str] = set()
    phrases: list[str] = []
    for match in _KEY_PHRASE_RE.finditer(text):
        phrase = match.group(0).strip().rstrip(".,;")
        lower = phrase.lower()
        if lower not in seen:
            seen.add(lower)
            phrases.append(phrase)
    return phrases


# ══════════════════════════════════════════════════════════════════════════
# SimpleLearningExtractor
# ══════════════════════════════════════════════════════════════════════════


class SimpleLearningExtractor:
    """In-memory :class:`~loom_ai.contracts_workflow.LearningExtractor`.

    Stores experiences, feedback signals, and strategy rewards in plain
    Python data structures.  Suitable for testing and single-process
    deployments.

    Satisfies :class:`~loom_ai.contracts_workflow.LearningExtractor` via
    structural subtyping -- no inheritance required.
    """

    def __init__(self) -> None:
        # experience_id -> {task, outcome, context, created_at}
        self._experiences: dict[str, dict] = {}

        # strategy -> {total_trials, total_reward, alpha, beta}
        self._strategies: dict[str, dict] = {}

    # -- LearningExtractor protocol ----------------------------------------

    async def detect_feedback(
        self, messages: list[ChatMessage]
    ) -> list[FeedbackSignal]:
        """Scan *messages* for implicit or explicit feedback signals.

        Only user messages are inspected.  Each message is tested against
        every compiled pattern; the first match per (message, type) pair
        is emitted.
        """
        signals: list[FeedbackSignal] = []
        for msg in messages:
            if msg.role != "user":
                continue
            seen_types: set[str] = set()
            for pattern, fb_type, confidence in _FEEDBACK_PATTERNS:
                if fb_type in seen_types:
                    continue
                if pattern.search(msg.content):
                    seen_types.add(fb_type)
                    signals.append(
                        FeedbackSignal(
                            type=fb_type,
                            content=msg.content,
                            confidence=confidence,
                            source_message=msg.content,
                        )
                    )
        return signals

    async def record_experience(
        self,
        task: str,
        outcome: str,
        *,
        context: dict | None = None,
    ) -> str:
        """Persist a task/outcome pair and return its UUID."""
        experience_id = str(uuid.uuid4())
        self._experiences[experience_id] = {
            "task": task,
            "outcome": outcome,
            "context": context or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return experience_id

    async def extract_learnings(self, experience_id: str) -> list[Learning]:
        """Derive actionable learnings from a stored experience.

        Key phrases are extracted from both the task description and the
        outcome text.  Each phrase becomes a separate
        :class:`~loom_ai.models_workflow.Learning`.
        """
        experience = self._experiences.get(experience_id)
        if experience is None:
            return []

        combined = f"{experience['task']}. {experience['outcome']}"
        phrases = _extract_key_phrases(combined)

        learnings: list[Learning] = []
        now = datetime.now(timezone.utc).isoformat()
        for phrase in phrases:
            learnings.append(
                Learning(
                    id=str(uuid.uuid4()),
                    content=phrase,
                    category="key_phrase",
                    source_experience=experience_id,
                    created_at=now,
                )
            )

        # Always produce at least one learning summarising the experience.
        if not learnings:
            learnings.append(
                Learning(
                    id=str(uuid.uuid4()),
                    content=f"Task: {experience['task']} -> {experience['outcome']}",
                    category="summary",
                    source_experience=experience_id,
                    created_at=now,
                )
            )

        return learnings

    async def update_strategy(
        self, strategy: str, outcome: str, *, reward: float
    ) -> None:
        """Record a reward observation for Thompson Sampling bandit state.

        Maintains cumulative trial count and total reward, plus Beta
        distribution parameters (alpha/beta) updated as:
        - success (reward >= 0.5): alpha += 1
        - failure (reward < 0.5):  beta  += 1
        """
        _ = outcome
        state = self._strategies.setdefault(
            strategy,
            {"total_trials": 0, "total_reward": 0.0, "alpha": 1.0, "beta": 1.0},
        )
        state["total_trials"] += 1
        state["total_reward"] += reward
        if reward >= 0.5:
            state["alpha"] += 1.0
        else:
            state["beta"] += 1.0
