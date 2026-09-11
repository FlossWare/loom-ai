import pytest

from loom_ai.backends.sqlite import SQLiteStorageBackend
from loom_ai.core_qualification import run
from loom_ai.models import Document


async def test_sqlite_document_survives_backend_recreation(tmp_path):
    database = tmp_path / "loom.sqlite3"
    document = Document(
        id="doc-1",
        title="SQLite test",
        content="durable",
        category="test",
        metadata={"verified": True, "event_ids": ["evt-1"]},
    )

    first = SQLiteStorageBackend(database)
    await first.store_document(document)
    await first.close()

    second = SQLiteStorageBackend(database)
    recovered = await second.get_document("doc-1")
    await second.close()

    assert recovered == document


@pytest.mark.asyncio
async def test_core_qualification_recovers_across_process_boundary(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOOM_STORAGE", "sqlite")
    monkeypatch.setenv("LOOM_SQLITE_PATH", str(tmp_path / "loom.sqlite3"))

    result = run(str(tmp_path))

    assert result["passed"] is True
    assert result["initial"]["verification"] == "passed"
    assert result["recovery"]["verification"] == "passed"
    assert result["recovery"]["provenance_event_ids"]
