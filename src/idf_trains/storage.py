"""Persistance des trajets sauvegardés (SQLite)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_journeys (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT,
    origin_id      TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (origin_id, destination_id)
);
"""


class DuplicateJourneyError(Exception):
    def __init__(self, existing_id: int):
        super().__init__(f"Trajet déjà sauvegardé (id {existing_id})")
        self.existing_id = existing_id


@dataclass
class JourneyRow:
    id: int
    name: str | None
    origin_id: str
    destination_id: str
    created_at: datetime


def _row(r: sqlite3.Row) -> JourneyRow:
    return JourneyRow(
        id=r["id"],
        name=r["name"],
        origin_id=r["origin_id"],
        destination_id=r["destination_id"],
        created_at=datetime.fromisoformat(r["created_at"]),
    )


class JourneyStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        # Une connexion par opération : simple et sûr entre threads
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self) -> list[JourneyRow]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM saved_journeys ORDER BY created_at, id").fetchall()
        return [_row(r) for r in rows]

    def get(self, journey_id: int) -> JourneyRow | None:
        with self._connect() as db:
            r = db.execute("SELECT * FROM saved_journeys WHERE id = ?", (journey_id,)).fetchone()
        return _row(r) if r else None

    def create(self, origin_id: str, destination_id: str, name: str | None) -> JourneyRow:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            existing = db.execute(
                "SELECT id FROM saved_journeys WHERE origin_id = ? AND destination_id = ?",
                (origin_id, destination_id),
            ).fetchone()
            if existing:
                raise DuplicateJourneyError(existing["id"])
            cur = db.execute(
                "INSERT INTO saved_journeys (name, origin_id, destination_id, created_at) "
                "VALUES (?, ?, ?, ?)",
                (name, origin_id, destination_id, created_at),
            )
            journey_id = cur.lastrowid
        return self.get(journey_id)  # type: ignore[return-value]

    def rename(self, journey_id: int, name: str | None) -> JourneyRow | None:
        with self._connect() as db:
            db.execute("UPDATE saved_journeys SET name = ? WHERE id = ?", (name, journey_id))
        return self.get(journey_id)

    def delete(self, journey_id: int) -> bool:
        with self._connect() as db:
            cur = db.execute("DELETE FROM saved_journeys WHERE id = ?", (journey_id,))
        return cur.rowcount > 0
