"""SQLite storage for documents, passages and unanswered questions.

This is the MVP stand-in for PostgreSQL with pgvector. Vector search compares
the query with every passage, which is fast enough for thousands of passages.
All SQL is in this module, so moving to PostgreSQL changes only this file.
"""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, name)
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL
);
-- The category list keeps Hindi vowel signs inside words.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content, tokenize = "unicode61 categories 'L* N* Co M*'"
);
CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE rowid = old.id;
END;
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    call_id TEXT,
    question TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_WORD = re.compile(r"[\wऀ-ॿ]+")


@dataclass(frozen=True)
class Chunk:
    id: int
    document: str
    content: str


class KnowledgeStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # One connection per operation keeps this safe across API threads.
        db = sqlite3.connect(self._path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

    def replace_document(
        self, tenant: str, name: str, model: str, chunks: list[str], vectors: np.ndarray
    ) -> int:
        """Store a document, replacing an earlier upload with the same name."""
        with self._connect() as db:
            db.execute("DELETE FROM documents WHERE tenant_id = ? AND name = ?", (tenant, name))
            document_id = db.execute(
                "INSERT INTO documents (tenant_id, name, model) VALUES (?, ?, ?)",
                (tenant, name, model),
            ).lastrowid
            for content, vector in zip(chunks, vectors, strict=True):
                chunk_id = db.execute(
                    "INSERT INTO chunks (document_id, content, embedding) VALUES (?, ?, ?)",
                    (document_id, content, vector.astype(np.float32).tobytes()),
                ).lastrowid
                db.execute(
                    "INSERT INTO chunks_fts (rowid, content) VALUES (?, ?)", (chunk_id, content)
                )
        return document_id

    def documents(self, tenant: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT d.id, d.name, d.created_at, COUNT(c.id) FROM documents d "
                "LEFT JOIN chunks c ON c.document_id = d.id "
                "WHERE d.tenant_id = ? GROUP BY d.id ORDER BY d.name",
                (tenant,),
            ).fetchall()
        return [
            {"id": id_, "name": name, "created_at": created, "chunks": count}
            for id_, name, created, count in rows
        ]

    def delete_document(self, tenant: str, document_id: int) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM documents WHERE tenant_id = ? AND id = ?", (tenant, document_id)
            )
        return cursor.rowcount > 0

    def vectors(self, tenant: str, model: str) -> tuple[list[Chunk], np.ndarray]:
        """Passages embedded with this model. Vectors from other models are not comparable."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.id, d.name, c.content, c.embedding FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE d.tenant_id = ? AND d.model = ?",
                (tenant, model),
            ).fetchall()
        chunks = [Chunk(id_, name, content) for id_, name, content, _ in rows]
        if not rows:
            return chunks, np.empty((0, 0), dtype=np.float32)
        return chunks, np.stack([np.frombuffer(row[3], dtype=np.float32) for row in rows])

    def keyword_ranking(self, tenant: str, query: str, limit: int) -> list[int]:
        """Chunk ids ordered by keyword relevance (BM25)."""
        words = [word for word in _WORD.findall(query) if len(word) > 2]
        if not words:
            return []
        # Quoting each word stops the caller's text being read as search syntax.
        match = " OR ".join(f'"{word}"' for word in words)
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.id FROM chunks_fts f JOIN chunks c ON c.id = f.rowid "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE chunks_fts MATCH ? AND d.tenant_id = ? ORDER BY bm25(chunks_fts) LIMIT ?",
                (match, tenant, limit),
            ).fetchall()
        return [row[0] for row in rows]

    def add_gap(self, tenant: str, question: str, call_id: str | None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO knowledge_gaps (tenant_id, call_id, question) VALUES (?, ?, ?)",
                (tenant, call_id, question),
            )

    def gaps(self, tenant: str, limit: int = 50) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT question, call_id, created_at FROM knowledge_gaps "
                "WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
                (tenant, limit),
            ).fetchall()
        return [{"question": q, "call_id": c, "created_at": t} for q, c, t in rows]
