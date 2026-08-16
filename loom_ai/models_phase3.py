"""Phase 3 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 3 protocols reference these types for their method
signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionBriefing:
    """Context provided when initializing a new orchestration session."""

    memories: list = field(default_factory=list)
    fleet_status: dict = field(default_factory=dict)
    preferences: dict = field(default_factory=dict)
    api_keys: list[str] = field(default_factory=list)
    initialized_at: str = ""


@dataclass
class WorkerInfo:
    """Descriptor for a registered worker node."""

    id: str
    name: str
    endpoint: str
    capabilities: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    status: str = ""


@dataclass
class WorkerStatus:
    """Health-check result for a single worker."""

    worker_id: str
    healthy: bool
    last_check: str
    latency_ms: float
    error: str | None = None


@dataclass
class DiversityReport:
    """Model usage distribution and dominance analysis."""

    model_distribution: dict = field(default_factory=dict)
    dominant_model: str | None = None
    dominance_ratio: float = 0.0
    is_healthy: bool = True


@dataclass
class CacheStats:
    """Prompt-cache utilization statistics."""

    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    tokens_saved: int = 0
    cost_saved: float = 0.0


@dataclass
class EvaluationResult:
    """Outcome of a multi-model evaluation harness run."""

    verdict: str
    scores: dict = field(default_factory=dict)
    reasoning: str = ""
    evaluator_models: list[str] = field(default_factory=list)


@dataclass
class FeedbackLoopRisk:
    """A single risk detected by feedback-loop analysis."""

    layer: str
    severity: float
    description: str
    metric_value: float
    threshold: float


@dataclass
class FeedbackLoopReport:
    """Summary of feedback-loop health analysis."""

    is_healthy: bool
    risks: list[FeedbackLoopRisk] = field(default_factory=list)
    analyzed_at: str = ""
    window_days: int = 7
