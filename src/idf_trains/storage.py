"""Persistance SQLite : trajets et itinéraires sauvegardés, cache des recherches d'adresses."""

from __future__ import annotations

import json
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


class SQLiteStore:
    """Base : une connexion par opération (simple et sûr entre threads)."""

    SCHEMA = ""

    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(self.SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


class JourneyStore(SQLiteStore):
    SCHEMA = SCHEMA

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


# --- Itinéraires sauvegardés (entre deux lieux quelconques) -------------------------------

ITINERARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_itineraries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT,
    origin_id      TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    origin         TEXT NOT NULL,  -- lieu complet en JSON (nom, type, coordonnées…)
    destination    TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (origin_id, destination_id)
);
"""


class DuplicateItineraryError(Exception):
    def __init__(self, existing_id: int):
        super().__init__(f"Itinéraire déjà sauvegardé (id {existing_id})")
        self.existing_id = existing_id


@dataclass
class ItineraryRow:
    id: int
    name: str | None
    origin: dict
    destination: dict
    created_at: datetime


def _itinerary_row(r: sqlite3.Row) -> ItineraryRow:
    return ItineraryRow(
        id=r["id"],
        name=r["name"],
        origin=json.loads(r["origin"]),
        destination=json.loads(r["destination"]),
        created_at=datetime.fromisoformat(r["created_at"]),
    )


class ItineraryStore(SQLiteStore):
    SCHEMA = ITINERARY_SCHEMA

    def list(self) -> list[ItineraryRow]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM saved_itineraries ORDER BY created_at, id").fetchall()
        return [_itinerary_row(r) for r in rows]

    def get(self, itinerary_id: int) -> ItineraryRow | None:
        with self._connect() as db:
            r = db.execute("SELECT * FROM saved_itineraries WHERE id = ?", (itinerary_id,)).fetchone()
        return _itinerary_row(r) if r else None

    def create(self, origin: dict, destination: dict, name: str | None) -> ItineraryRow:
        with self._connect() as db:
            existing = db.execute(
                "SELECT id FROM saved_itineraries WHERE origin_id = ? AND destination_id = ?",
                (origin["id"], destination["id"]),
            ).fetchone()
            if existing:
                raise DuplicateItineraryError(existing["id"])
            cur = db.execute(
                "INSERT INTO saved_itineraries "
                "(name, origin_id, destination_id, origin, destination, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    name,
                    origin["id"],
                    destination["id"],
                    json.dumps(origin, ensure_ascii=False),
                    json.dumps(destination, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            itinerary_id = cur.lastrowid
        return self.get(itinerary_id)  # type: ignore[return-value]

    def rename(self, itinerary_id: int, name: str | None) -> ItineraryRow | None:
        with self._connect() as db:
            db.execute("UPDATE saved_itineraries SET name = ? WHERE id = ?", (name, itinerary_id))
        return self.get(itinerary_id)

    def delete(self, itinerary_id: int) -> bool:
        with self._connect() as db:
            cur = db.execute("DELETE FROM saved_itineraries WHERE id = ?", (itinerary_id,))
        return cur.rowcount > 0


# --- Cache persistant des recherches d'adresses -------------------------------------------

PLACE_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS place_searches (
    query      TEXT PRIMARY KEY,
    results    TEXT NOT NULL,  -- liste de lieux en JSON
    created_at REAL NOT NULL,  -- horodatage Unix
    hits       INTEGER NOT NULL DEFAULT 0
);
"""


class PlaceSearchStore(SQLiteStore):
    """Résultats des recherches d'adresses, conservés entre redémarrages pour ménager le quota IDFM."""

    SCHEMA = PLACE_CACHE_SCHEMA

    def __init__(self, path: Path | str, max_age: float = 30 * 86400):
        super().__init__(path)
        self.max_age = max_age

    def get(self, query: str) -> list[dict] | None:
        with self._connect() as db:
            r = db.execute(
                "SELECT results FROM place_searches WHERE query = ? AND created_at > ?",
                (query, _now() - self.max_age),
            ).fetchone()
            if r is None:
                return None
            db.execute("UPDATE place_searches SET hits = hits + 1 WHERE query = ?", (query,))
        return json.loads(r["results"])

    def set(self, query: str, results: list[dict]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO place_searches (query, results, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(query) DO UPDATE SET results = excluded.results, "
                "created_at = excluded.created_at",
                (query, json.dumps(results, ensure_ascii=False), _now()),
            )

    def purge(self) -> int:
        """Supprime les entrées expirées ; renvoie leur nombre."""
        with self._connect() as db:
            cur = db.execute(
                "DELETE FROM place_searches WHERE created_at <= ?", (_now() - self.max_age,)
            )
        return cur.rowcount


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()
