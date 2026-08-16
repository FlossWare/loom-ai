"""Phase 3 protocol definitions for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required. All methods are
async (except where synchronous semantics are appropriate). Nothing
outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_phase3 import (
        CacheStats,
        DiversityReport,
        EvaluationResult,
        FeedbackLoopReport,
        SessionBriefing,
        WorkerInfo,
    )


@runtime_checkable
class SessionInitializer(Protocol):
    """Bootstrap an orchestration session with fleet context."""

    async def initialize(self, *, context: Any | None = None) -> SessionBriefing:
        """Load memories, fleet status, preferences, and API keys.

        *context* is optional caller-supplied data that implementations
        may use to tailor the briefing.
        """
        ...


@runtime_checkable
class WorkerRegistry(Protocol):
    """Registry for managing fleet worker nodes."""

    async def register(self, worker: WorkerInfo) -> None:
        """Add a worker to the registry."""
        ...

    async def deregister(self, worker_id: str) -> None:
        """Remove a worker from the registry."""
        ...

    async def health_check(self) -> dict:
        """Return the health status of all registered workers."""
        ...

    async def model_diversity(self) -> DiversityReport:
        """Analyze model usage distribution across workers."""
        ...


@runtime_checkable
class CachePolicy(Protocol):
    """Prompt-caching strategy for provider-specific cache hints."""

    def apply_cache_hints(self, messages: list, *, provider: str) -> list:
        """Annotate *messages* with cache-control hints for *provider*.

        Returns a new list of messages with provider-specific caching
        directives applied.
        """
        ...

    async def cache_stats(self) -> CacheStats:
        """Return current cache utilization statistics."""
        ...


@runtime_checkable
class EvaluationHarness(Protocol):
    """Multi-model adversarial evaluation of task outputs."""

    async def evaluate(
        self,
        output: Any,
        *,
        task: str,
        models: list[str],
    ) -> EvaluationResult:
        """Evaluate *output* against *task* using the specified *models*.

        Returns a verdict (ACCEPT, ACCEPT_WITH_RESERVATIONS, or REJECT)
        with scores and reasoning.
        """
        ...


@runtime_checkable
class FeedbackLoopDetector(Protocol):
    """Detection of self-referential feedback loops in the fleet."""

    async def analyze(self, *, window_days: int = 7) -> FeedbackLoopReport:
        """Run feedback-loop analysis over the given time window.

        Checks for model dominance, evaluator-generator coupling,
        reward hacking, and concept collapse.
        """
        ...

    async def is_healthy(self) -> bool:
        """Return ``True`` if no critical feedback-loop risks exist."""
        ...


@runtime_checkable
class HumanInTheLoop(Protocol):
    """Interface for requesting human input during orchestration."""

    async def request_input(
        self,
        prompt: str,
        *,
        options: list[str] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Present *prompt* to a human and return their response.

        *options* constrains valid responses.  *timeout* is the maximum
        wait time in seconds before raising.
        """
        ...

    async def notify(self, message: str) -> None:
        """Send a one-way notification to the human operator."""
        ...
