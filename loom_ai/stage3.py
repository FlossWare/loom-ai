"""Bounded real-worker pipeline used by the Stage 3 server dogfood.

This module deliberately contains no model or provider integration. The workers
perform deterministic filesystem work so the server can prove real execution,
verification, evidence, and failure propagation without introducing a gateway.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from loom_ai.worker import WorkerContext, WorkerResult, WorkerStatus

DEFAULT_ARTIFACT = "/tmp/loom-stage3-artifact.txt"
MAX_GOAL_BYTES = 4096


def artifact_path() -> Path:
    """Return the bounded artifact location used by the Stage 3 dogfood."""
    return Path(os.environ.get("LOOM_STAGE3_ARTIFACT", DEFAULT_ARTIFACT))


def artifact_content(context: WorkerContext) -> str:
    """Build deterministic artifact content from the submitted Intent.

    Raises:
        TypeError: if the Intent goal is not a string.
        ValueError: if the UTF-8 goal exceeds the Stage 3 limit.
    """
    goal = context.intent.goal
    if not isinstance(goal, str):
        raise TypeError("Intent goal must be a string")
    encoded = goal.encode("utf-8")
    if len(encoded) > MAX_GOAL_BYTES:
        raise ValueError("Intent goal exceeds Stage 3 limit")
    goal_digest = hashlib.sha256(encoded).hexdigest()
    return (
        "Loom Stage 3\n"
        f"intent_id={context.intent.intent_id}\n"
        f"goal_sha256={goal_digest}\n"
    )


class ArtifactWriter:
    """Perform a bounded, deterministic filesystem change."""

    worker_id = "artifact-writer"

    def execute(self, context: WorkerContext) -> WorkerResult:
        try:
            content = artifact_content(context)
            path = artifact_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILED,
                error=str(exc),
            )

        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"path": str(path), "bytes": len(content.encode("utf-8"))},
            evidence=(
                {
                    "type": "artifact-written",
                    "worker_id": self.worker_id,
                    "path": str(path),
                },
            ),
        )


class ArtifactVerifier:
    """Verify the exact artifact produced by :class:`ArtifactWriter`."""

    worker_id = "artifact-verifier"

    def execute(self, context: WorkerContext) -> WorkerResult:
        path = artifact_path()
        try:
            actual = path.read_text(encoding="utf-8")
            expected = artifact_content(context)
        except (OSError, TypeError, ValueError) as exc:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILED,
                error=str(exc),
            )

        if actual != expected:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILED,
                error="artifact content does not match the submitted Intent",
            )

        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"path": str(path), "verified": True},
            evidence=(
                {
                    "type": "artifact-verified",
                    "worker_id": self.worker_id,
                    "path": str(path),
                },
            ),
        )
