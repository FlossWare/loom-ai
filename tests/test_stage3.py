from pathlib import Path

from loom_ai.intent import Intent
from loom_ai.server import _stage3_arbiter
from loom_ai.worker import WorkerContext


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
        "goal=prove real worker execution\n"
    )
    evidence_types = [item["type"] for item in result.evidence]
    assert "artifact-written" in evidence_types
    assert "artifact-verified" in evidence_types
