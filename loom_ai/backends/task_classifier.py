"""Rule-based task classifier for loom-ai.

Categorises natural-language task descriptions into well-known task
categories (e.g. ``"simple_qa"``, ``"research"``, ``"code_generation"``,
``"consensus"``) and returns execution blueprints describing how the
orchestration engine should run them.

The classifier is intentionally simple -- keyword / pattern matching --
so that it carries zero external dependencies and can be replaced by a
learned classifier behind the same ``TaskClassifier`` protocol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# -- Data models -----------------------------------------------------------


@dataclass
class ExecutionBlueprint:
    """Describes how a task should be executed.

    Attributes:
        category: The classified task category.
        models: Suggested model identifiers to use.
        use_consensus: Whether to run multi-model consensus.
        timeout_seconds: Maximum wall-clock time for execution.
        max_retries: How many times to retry on transient failure.
        metadata: Arbitrary extra configuration.
    """

    category: str
    models: list[str] = field(default_factory=list)
    use_consensus: bool = False
    timeout_seconds: float = 30.0
    max_retries: int = 1
    metadata: dict = field(default_factory=dict)


# -- Protocol --------------------------------------------------------------


@runtime_checkable
class TaskClassifier(Protocol):
    """Classify a task description and return an execution blueprint."""

    def classify(self, task: str) -> ExecutionBlueprint:
        """Analyse *task* and return a suitable ``ExecutionBlueprint``."""
        ...


# -- Built-in rule-based implementation ------------------------------------

# Each rule is a ``(compiled_pattern, category)`` pair evaluated in order.
# The first match wins.

_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(consensus|vote|agree|disagree|debate|multi[- ]?model)\b",
            re.IGNORECASE,
        ),
        "consensus",
    ),
    (
        re.compile(
            r"\b(write|generate|implement|refactor|code|function|class|module)\b",
            re.IGNORECASE,
        ),
        "code_generation",
    ),
    (
        re.compile(
            r"\b(research|investigate|explore|analyse|analyze|compare|review|study)\b",
            re.IGNORECASE,
        ),
        "research",
    ),
    (
        re.compile(
            r"\b(summarise|summarize|summary|tldr|tl;dr|recap|condense|digest)\b",
            re.IGNORECASE,
        ),
        "summarization",
    ),
    (
        re.compile(
            r"\b(translate|translation|convert language)\b",
            re.IGNORECASE,
        ),
        "translation",
    ),
]

# Category -> default blueprint settings.
_DEFAULTS: dict[str, dict] = {
    "simple_qa": {
        "models": ["fast"],
        "use_consensus": False,
        "timeout_seconds": 15.0,
        "max_retries": 1,
    },
    "research": {
        "models": ["fast", "balanced"],
        "use_consensus": False,
        "timeout_seconds": 60.0,
        "max_retries": 2,
    },
    "code_generation": {
        "models": ["balanced"],
        "use_consensus": False,
        "timeout_seconds": 45.0,
        "max_retries": 2,
    },
    "consensus": {
        "models": ["fast", "balanced", "quality"],
        "use_consensus": True,
        "timeout_seconds": 90.0,
        "max_retries": 1,
    },
    "summarization": {
        "models": ["fast"],
        "use_consensus": False,
        "timeout_seconds": 30.0,
        "max_retries": 1,
    },
    "translation": {
        "models": ["balanced"],
        "use_consensus": False,
        "timeout_seconds": 30.0,
        "max_retries": 1,
    },
}


class RuleBasedTaskClassifier:
    """Classify tasks using ordered keyword rules.

    Parameters
    ----------
    rules:
        Optional custom rules as ``(compiled_pattern, category)`` pairs.
        Falls back to the module-level ``_RULES`` when not supplied.
    defaults:
        Optional per-category default blueprint overrides.
    """

    def __init__(
        self,
        *,
        rules: list[tuple[re.Pattern[str], str]] | None = None,
        defaults: dict[str, dict] | None = None,
    ) -> None:
        self._rules = rules if rules is not None else _RULES
        self._defaults = defaults if defaults is not None else _DEFAULTS

    # -- TaskClassifier protocol -------------------------------------------

    def classify(self, task: str) -> ExecutionBlueprint:
        """Return an ``ExecutionBlueprint`` for *task*."""
        category = self._match(task)
        overrides = self._defaults.get(category, {})
        return ExecutionBlueprint(
            category=category,
            models=list(overrides.get("models", ["fast"])),
            use_consensus=overrides.get("use_consensus", False),
            timeout_seconds=overrides.get("timeout_seconds", 30.0),
            max_retries=overrides.get("max_retries", 1),
        )

    # -- internals ---------------------------------------------------------

    def _match(self, task: str) -> str:
        """Return the first matching category, or ``"simple_qa"``."""
        for pattern, category in self._rules:
            if pattern.search(task):
                return category
        return "simple_qa"
