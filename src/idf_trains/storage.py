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
    -- Horaire par défaut : now | departure | arrival, avec date (AAAA-MM-JJ) et heure (HH:MM) facultatives
    schedule_mode  TEXT NOT NULL DEFAULT 'now',
    schedule_date  TEXT,
    schedule_time  TEXT,
    UNIQUE (origin_id, destination_id)
);
"""

# Colonnes ajoutées après la première version : migrées automatiquement sur les bases existantes
ITINERARY_MIGRATIONS = {
    "schedule_mode": "ALTER TABLE saved_itineraries ADD COLUMN schedule_mode TEXT NOT NULL DEFAULT 'now'",
    "schedule_date": "ALTER TABLE saved_itineraries ADD COLUMN schedule_date TEXT",
    "schedule_time": "ALTER TABLE saved_itineraries ADD COLUMN schedule_time TEXT",
}


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
    schedule: dict  # {"mode": ..., "date": ... | None, "time": ... | None}


def _itinerary_row(r: sqlite3.Row) -> ItineraryRow:
    return ItineraryRow(
        id=r["id"],
        name=r["name"],
        origin=json.loads(r["origin"]),
        destination=json.loads(r["destination"]),
        created_at=datetime.fromisoformat(r["created_at"]),
        schedule={"mode": r["schedule_mode"], "date": r["schedule_date"], "time": r["schedule_time"]},
    )


NO_SCHEDULE = {"mode": "now", "date": None, "time": None}


class ItineraryStore(SQLiteStore):
    SCHEMA = ITINERARY_SCHEMA

    def __init__(self, path: Path | str):
        super().__init__(path)
        with self._connect() as db:
            columns = {r["name"] for r in db.execute("PRAGMA table_info(saved_itineraries)")}
            for column, ddl in ITINERARY_MIGRATIONS.items():
                if column not in columns:
                    db.execute(ddl)

    def list(self) -> list[ItineraryRow]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM saved_itineraries ORDER BY created_at, id").fetchall()
        return [_itinerary_row(r) for r in rows]

    def get(self, itinerary_id: int) -> ItineraryRow | None:
        with self._connect() as db:
            r = db.execute("SELECT * FROM saved_itineraries WHERE id = ?", (itinerary_id,)).fetchone()
        return _itinerary_row(r) if r else None

    @staticmethod
    def _check_unique(db, origin_id: str, destination_id: str, exclude_id: int | None = None) -> None:
        existing = db.execute(
            "SELECT id FROM saved_itineraries WHERE origin_id = ? AND destination_id = ? AND id IS NOT ?",
            (origin_id, destination_id, exclude_id),
        ).fetchone()
        if existing:
            raise DuplicateItineraryError(existing["id"])

    def create(
        self, origin: dict, destination: dict, name: str | None, schedule: dict | None = None
    ) -> ItineraryRow:
        schedule = schedule or NO_SCHEDULE
        with self._connect() as db:
            self._check_unique(db, origin["id"], destination["id"])
            cur = db.execute(
                "INSERT INTO saved_itineraries (name, origin_id, destination_id, origin, destination, "
                "created_at, schedule_mode, schedule_date, schedule_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    origin["id"],
                    destination["id"],
                    json.dumps(origin, ensure_ascii=False),
                    json.dumps(destination, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                    schedule["mode"],
                    schedule["date"],
                    schedule["time"],
                ),
            )
            itinerary_id = cur.lastrowid
        return self.get(itinerary_id)  # type: ignore[return-value]

    def update(self, itinerary_id: int, **changes) -> ItineraryRow | None:
        """Mise à jour partielle : name, origin, destination, schedule (seuls les champs fournis)."""
        current = self.get(itinerary_id)
        if current is None:
            return None
        origin = changes.get("origin", current.origin)
        destination = changes.get("destination", current.destination)
        schedule = changes.get("schedule", current.schedule)
        name = changes["name"] if "name" in changes else current.name
        with self._connect() as db:
            self._check_unique(db, origin["id"], destination["id"], exclude_id=itinerary_id)
            db.execute(
                "UPDATE saved_itineraries SET name = ?, origin_id = ?, destination_id = ?, origin = ?, "
                "destination = ?, schedule_mode = ?, schedule_date = ?, schedule_time = ? WHERE id = ?",
                (
                    name,
                    origin["id"],
                    destination["id"],
                    json.dumps(origin, ensure_ascii=False),
                    json.dumps(destination, ensure_ascii=False),
                    schedule["mode"],
                    schedule["date"],
                    schedule["time"],
                    itinerary_id,
                ),
            )
        return self.get(itinerary_id)

    def rename(self, itinerary_id: int, name: str | None) -> ItineraryRow | None:
        return self.update(itinerary_id, name=name)

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


# --- Suivi de la consommation des API IDFM ----------------------------------------------

USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,     -- horodatage Unix
    day         TEXT NOT NULL,     -- date à Paris (AAAA-MM-JJ), jour de remise à zéro des quotas
    hour        INTEGER NOT NULL,  -- heure à Paris
    api         TEXT NOT NULL,     -- realtime | navitia
    endpoint    TEXT NOT NULL,     -- stop-monitoring | places | journeys
    status      INTEGER NOT NULL,  -- code HTTP (0 = erreur réseau)
    duration_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS api_calls_day ON api_calls (day);
CREATE TABLE IF NOT EXISTS cache_hits (
    day    TEXT NOT NULL,
    api    TEXT NOT NULL,
    count  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, api)
);
"""


class UsageStore(SQLiteStore):
    """Journal des appels sortants vers IDFM et des requêtes évitées grâce au cache."""

    SCHEMA = USAGE_SCHEMA

    def record_call(self, api: str, endpoint: str, status: int, duration_ms: int, at: datetime) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO api_calls (ts, day, hour, api, endpoint, status, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (at.timestamp(), at.date().isoformat(), at.hour, api, endpoint, status, duration_ms),
            )

    def record_cache_hit(self, api: str, at: datetime) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO cache_hits (day, api, count) VALUES (?, ?, 1) "
                "ON CONFLICT(day, api) DO UPDATE SET count = count + 1",
                (at.date().isoformat(), api),
            )

    def daily(self, since: str) -> list[dict]:
        """Par jour et par API : appels, erreurs, requêtes servies par le cache."""
        with self._connect() as db:
            calls = db.execute(
                "SELECT day, api, COUNT(*) AS calls, SUM(status <> 200) AS errors "
                "FROM api_calls WHERE day >= ? GROUP BY day, api",
                (since,),
            ).fetchall()
            hits = db.execute(
                "SELECT day, api, count FROM cache_hits WHERE day >= ?", (since,)
            ).fetchall()
        rows: dict[tuple, dict] = {}
        for r in calls:
            rows[(r["day"], r["api"])] = {
                "day": r["day"], "api": r["api"], "calls": r["calls"], "errors": r["errors"] or 0, "cache_hits": 0
            }
        for r in hits:
            row = rows.setdefault(
                (r["day"], r["api"]), {"day": r["day"], "api": r["api"], "calls": 0, "errors": 0, "cache_hits": 0}
            )
            row["cache_hits"] = r["count"]
        return sorted(rows.values(), key=lambda r: (r["day"], r["api"]))

    def hourly(self, day: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT hour, api, COUNT(*) AS calls FROM api_calls WHERE day = ? GROUP BY hour, api",
                (day,),
            ).fetchall()
        return [dict(r) for r in rows]

    def by_endpoint(self, day: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT api, endpoint, COUNT(*) AS calls, SUM(status <> 200) AS errors, "
                "CAST(AVG(duration_ms) AS INTEGER) AS avg_ms "
                "FROM api_calls WHERE day = ? GROUP BY api, endpoint ORDER BY calls DESC",
                (day,),
            ).fetchall()
        return [dict(r) | {"errors": r["errors"] or 0} for r in rows]

    def recent(self, limit: int = 30) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT ts, api, endpoint, status, duration_ms FROM api_calls ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def purge(self, before_day: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM api_calls WHERE day < ?", (before_day,))
            db.execute("DELETE FROM cache_hits WHERE day < ?", (before_day,))


# --- Page d'accueil : éléments choisis et leur ordre -------------------------------------

HOME_SCHEMA = """
CREATE TABLE IF NOT EXISTS home_items (
    kind     TEXT NOT NULL CHECK (kind IN ('journey', 'itinerary')),
    ref_id   INTEGER NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (kind, ref_id)
);
"""


class HomeStore(SQLiteStore):
    """Trajets et itinéraires sauvegardés affichés sur la page d'accueil, dans l'ordre choisi."""

    SCHEMA = HOME_SCHEMA

    def list(self) -> list[tuple[str, int]]:
        with self._connect() as db:
            rows = db.execute("SELECT kind, ref_id FROM home_items ORDER BY position").fetchall()
        return [(r["kind"], r["ref_id"]) for r in rows]

    def replace(self, items: list[tuple[str, int]]) -> None:
        """Remplace toute la sélection (dans une seule transaction)."""
        with self._connect() as db:
            db.execute("DELETE FROM home_items")
            db.executemany(
                "INSERT INTO home_items (kind, ref_id, position) VALUES (?, ?, ?)",
                [(kind, ref_id, pos) for pos, (kind, ref_id) in enumerate(items)],
            )

    def remove(self, kind: str, ref_id: int) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM home_items WHERE kind = ? AND ref_id = ?", (kind, ref_id))
