"""Référentiel des gares ferroviaires (chargé depuis data/stations.json)."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from .models import Line, Station

# Mots ignorés dans la recherche approximative (s'il reste d'autres mots)
STOPWORDS = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "sur", "sous", "en", "gare", "station"}
ABBREVIATIONS = {"st": "saint", "ste": "sainte"}


def _token_score(query_token: str, candidates: list[str]) -> float:
    """Meilleure similarité entre un mot recherché et les mots d'une gare (0..1)."""
    best = 0.0
    for cand in candidates:
        if cand == query_token:
            return 1.0
        if len(query_token) >= 3 and cand.startswith(query_token):
            best = max(best, 0.95)  # « chat » -> « chatelet »
        else:
            best = max(best, SequenceMatcher(None, query_token, cand).ratio())
    return best


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

    def search_by_name(
        self, name: str, limit: int = 10, min_score: float = 0.65
    ) -> list[tuple[Station, float]]:
        """Recherche approximative par nom, tolérante aux fautes de frappe.

        Score (0..1) = moyenne, sur les mots recherchés, de la meilleure similarité avec un mot
        du nom ou de la commune, combinée à la similarité du nom complet.
        """
        query = " ".join(ABBREVIATIONS.get(t, t) for t in normalize(name).split())
        if not query:
            return []
        tokens = query.split()
        tokens = [t for t in tokens if t not in STOPWORDS] or tokens

        scored = []
        for station in self.stations.values():
            station_name = normalize(station.name)
            if station_name == query:
                scored.append((station, 1.0))
                continue
            candidates = self._search_keys[station.id].split()
            token_score = sum(_token_score(t, candidates) for t in tokens) / len(tokens)
            full_score = SequenceMatcher(None, query, station_name).ratio()
            score = round(min(0.99, 0.75 * token_score + 0.25 * full_score), 3)
            if score >= min_score:
                scored.append((station, score))

        scored.sort(key=lambda item: (-item[1], item[0].name))
        return scored[:limit]
