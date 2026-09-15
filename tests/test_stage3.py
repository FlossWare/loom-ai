from pathlib import Path

from loom_ai.intent import Intent
from loom_ai.server import _stage3_arbiter
from loom_ai.stage3 import ArtifactVerifier, MAX_GOAL_BYTES
from loom_ai.worker import WorkerContext, WorkerStatus


def test_stage3_writes_and_verifies_artifact(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact.txt"
    monkeypatch.setenv("LOOM_STAGE3_ARTIFACT", str(artifact))

    intent = Intent(goal="prove real worker execution", intent_id="stage3-test")
    result = _stage3_arbiter().execute(WorkerContext(intent=intent))

    assert result.successful
    assert [item.worker_id for item in result.output] == [
        "artifact-writer",
        "artifact-verifier",
    ]
    assert artifact.read_text(encoding="utf-8") == (
        "Loom Stage 3\n"
        "intent_id=stage3-test\n"
        "goal_sha256=dc06a7f1a04a327e330447bdadcd8cdef6e8fb2c0e4daf22ff0ffa055181083d\n"
    )
    evidence_types = [item["type"] for item in result.evidence]
    assert "artifact-written" in evidence_types
    assert "artifact-verified" in evidence_types


def test_stage3_rejects_oversized_goal(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact.txt"
    monkeypatch.setenv("LOOM_STAGE3_ARTIFACT", str(artifact))

    intent = Intent(goal="x" * (MAX_GOAL_BYTES + 1), intent_id="oversized")
    result = _stage3_arbiter().execute(WorkerContext(intent=intent))

    assert not result.successful
    assert result.output[0].worker_id == "artifact-writer"
    assert result.output[0].status is WorkerStatus.FAILED
    assert "exceeds Stage 3 limit" in result.output[0].error
    assert not artifact.exists()


def test_stage3_verifier_rejects_missing_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    artifact = tmp_path / "missing.txt"
    monkeypatch.setenv("LOOM_STAGE3_ARTIFACT", str(artifact))

    intent = Intent(goal="verify missing artifact", intent_id="missing")
    result = ArtifactVerifier().execute(WorkerContext(intent=intent))

    assert result.status is WorkerStatus.FAILED
    assert "No such file" in result.error


def test_stage3_verifier_rejects_content_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("not the expected artifact", encoding="utf-8")
    monkeypatch.setenv("LOOM_STAGE3_ARTIFACT", str(artifact))

    intent = Intent(goal="verify mismatch", intent_id="mismatch")
    result = ArtifactVerifier().execute(WorkerContext(intent=intent))

    assert result.status is WorkerStatus.FAILED
    assert "does not match" in result.error
