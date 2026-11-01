"""Référentiel des gares ferroviaires (chargé depuis data/stations.json)."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .models import Line, Station


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Châtelet - Les Halles » -> « chatelet les halles »."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class StationRepository:
    def __init__(self, data: dict):
        self.lines: dict[str, Line] = {
            lid: Line(id=lid, name=raw["name"], mode=raw["mode"]) for lid, raw in data["lines"].items()
        }
        self.stations: dict[str, Station] = {}
        self._search_keys: dict[str, str] = {}
        for raw in data["stations"]:
            station = Station(
                id=raw["id"],
                name=raw["name"],
                city=raw["city"],
                lat=raw["lat"],
                lon=raw["lon"],
                lines=[self.lines[lid] for lid in raw["lines"]],
            )
            self.stations[station.id] = station
            self._search_keys[station.id] = normalize(f"{station.name} {station.city}")

    @classmethod
    def from_file(cls, path: Path) -> StationRepository:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def get(self, station_id: str) -> Station | None:
        return self.stations.get(station_id)

    def line(self, line_id: str) -> Line | None:
        return self.lines.get(line_id)

    def search(self, query: str = "", line: str | None = None, limit: int = 20) -> list[Station]:
        tokens = normalize(query).split()
        line_name = line.upper() if line else None
        results = []
        for station in self.stations.values():
            key = self._search_keys[station.id]
            if not all(t in key for t in tokens):
                continue
            if line_name and not any(l.name.upper() == line_name for l in station.lines):
                continue
            results.append(station)

        q = " ".join(tokens)
        # Correspondance exacte, puis début de nom, puis ordre alphabétique
        results.sort(
            key=lambda s: (normalize(s.name) != q, not normalize(s.name).startswith(q), s.name)
        )
        return results[:limit]
