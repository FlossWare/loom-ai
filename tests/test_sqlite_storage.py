from loom_ai.backends.sqlite import SQLiteStorageBackend
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
