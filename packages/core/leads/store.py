"""SQLite storage for leads, calls and transcripts (MVP stand-in for PostgreSQL)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from packages.core.leads.models import LeadFacts
from packages.core.leads.redact import redact, redact_values

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    facts TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    score INTEGER,
    grade TEXT,
    follow_up INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT,
    sentiment TEXT,
    sentiment_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class LeadStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

    def start_call(self, call_id: str, lead_id: str, tenant: str = "default") -> LeadFacts:
        """Record the call and return what earlier calls learned about this lead."""
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO leads (id, tenant_id) VALUES (?, ?)", (lead_id, tenant)
            )
            db.execute("INSERT OR IGNORE INTO calls (id, lead_id) VALUES (?, ?)", (call_id, lead_id))
            (facts,) = db.execute("SELECT facts FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return LeadFacts.model_validate_json(facts)

    def add_turn(
        self, turn_id: str, call_id: str, speaker: str, text: str, language: str | None
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO turns (id, call_id, speaker, text, language) "
                "VALUES (?, ?, ?, ?, ?)",
                (turn_id, call_id, speaker, redact(text), language),
            )

    def save_analysis(
        self,
        call_id: str,
        lead_id: str,
        facts: LeadFacts,
        score: int,
        grade: str,
        follow_up: bool,
        turn_ids: list[str],
        sentiment: str,
        reason: str,
    ) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE leads SET facts = ? WHERE id = ?",
                (json.dumps(redact_values(facts.model_dump()), ensure_ascii=False), lead_id),
            )
            db.execute(
                "UPDATE calls SET score = ?, grade = ?, follow_up = ? WHERE id = ?",
                (score, grade, int(follow_up), call_id),
            )
            db.executemany(
                "UPDATE turns SET sentiment = ?, sentiment_reason = ? WHERE id = ?",
                [(sentiment, redact(reason), turn_id) for turn_id in turn_ids],
            )

    def end_call(self, call_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE calls SET ended_at = CURRENT_TIMESTAMP WHERE id = ?", (call_id,))

    def call(self, call_id: str) -> dict | None:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
            if row is None:
                return None
            turns = db.execute(
                "SELECT speaker, text, language, sentiment, sentiment_reason FROM turns "
                "WHERE call_id = ? ORDER BY rowid",
                (call_id,),
            ).fetchall()
        return {**dict(row), "turns": [dict(turn) for turn in turns]}

    def delete_lead(self, lead_id: str) -> bool:
        """Erase the lead with all calls and transcripts."""
        with self._connect() as db:
            db.execute("PRAGMA secure_delete = ON")
            cursor = db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        return cursor.rowcount > 0
