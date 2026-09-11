"""SQLite-backed document storage.

SQLite is part of the Python standard library and provides a durable local
storage backend without requiring an external database service. The backend
implements the document portion of StorageBackend durably and keeps chunk,
embedding, and other secondary operations in-process through
MemoryStorageBackend. Those secondary data are therefore not durable across a
process boundary and are intentionally outside this qualification backend's
guarantee.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from loom_ai.backends.memory import MemoryStorageBackend
from loom_ai.models import Document


class SQLiteStorageBackend(MemoryStorageBackend):
    """SQLite documents with in-memory secondary data."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def is_idempotent(self) -> bool:
        return True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    url TEXT NOT NULL,
                    category TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    async def store_document(self, document: Document) -> str:
        metadata = json.dumps(document.metadata, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (id, title, content, url, category, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    url=excluded.url,
                    category=excluded.category,
                    metadata=excluded.metadata,
                    created_at=excluded.created_at
                """,
                (
                    document.id,
                    document.title,
                    document.content,
                    document.url,
                    document.category,
                    metadata,
                    document.created_at,
                ),
            )
        self._documents[document.id] = document
        return document.id

    async def get_document(self, document_id: str) -> Document | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, content, url, category, metadata, created_at
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()

        if row is None:
            return None
        return Document(
            id=row[0],
            title=row[1],
            content=row[2],
            url=row[3],
            category=row[4],
            metadata=json.loads(row[5]),
            created_at=row[6],
        )

    async def list_documents(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, content, url, category, metadata, created_at
                FROM documents
                ORDER BY rowid
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

        return [
            Document(
                id=row[0],
                title=row[1],
                content=row[2],
                url=row[3],
                category=row[4],
                metadata=json.loads(row[5]),
                created_at=row[6],
            )
            for row in rows
        ]

    async def delete_document(self, document_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM documents WHERE id = ?", (document_id,)
            )
            deleted = cursor.rowcount > 0
        self._documents.pop(document_id, None)
        return deleted

    async def count_documents(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0])

    async def close(self) -> None:
        """Close the backend; SQLite connections are opened per operation."""
        return None
