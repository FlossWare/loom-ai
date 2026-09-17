"""Core Loom runtime primitives.

The canonical execution model is intentionally small:

    Intent -> Arbiter -> Worker -> result

Intent describes the desired outcome. Worker is the fundamental executable
abstraction. Arbiter is a composable Worker that coordinates Workers.

The HTTP server is only a transport boundary. Provider/model access,
evaluation, strategies, persistence, retrieval, and cross-cutting capabilities
belong to their dedicated repositories and integrate through Workers.
"""

from loom_ai.arbiter import Arbiter, ArbiterDecision, WorkerEvaluation
from loom_ai.intent import Intent, IntentParseError
from loom_ai.model import ModelProvider, ModelRequest, ModelResponse
from loom_ai.model_worker import ModelWorker
from loom_ai.server import LoomServer
from loom_ai.worker import Worker, WorkerContext, WorkerResult, WorkerStatus

__all__ = [
    "Arbiter",
    "ArbiterDecision",
    "Intent",
    "IntentParseError",
    "LoomServer",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ModelWorker",
    "Worker",
    "WorkerContext",
    "WorkerEvaluation",
    "WorkerResult",
    "WorkerStatus",
]

__version__ = "0.1"
