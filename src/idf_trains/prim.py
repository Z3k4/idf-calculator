"""Client de l'API PRIM « Prochains passages » (SIRI Lite StopMonitoring) et conversion simplifiée."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from .cache import Cache, MemoryCache
from .models import Departure, Line
from .stations import StationRepository


class PrimError(Exception):
    """Erreur lors de l'appel à PRIM."""


class PrimConfigError(PrimError):
    """Configuration absente (clé API)."""


CacheStatus = Literal["HIT", "MISS", "STALE"]


@dataclass
class StopMonitoring:
    data: dict
    fetched_at: datetime
    cache: CacheStatus

    @property
    def age_seconds(self) -> int:
        return max(0, int((datetime.now(timezone.utc) - self.fetched_at).total_seconds()))


class PrimClient:
    """Client PRIM avec cache.

    - une entrée est « fraîche » pendant `cache_ttl` secondes : servie sans appeler PRIM ;
    - elle reste conservée jusqu'à `stale_ttl` secondes : servie seulement si PRIM est en erreur ;
    - les requêtes simultanées sur une même gare ne déclenchent qu'un seul appel PRIM.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        url: str,
        cache: Cache | None = None,
        cache_ttl: float = 30.0,
        stale_ttl: float = 300.0,
    ):
        self.http = http
        self.api_key = api_key
        self.url = url
        self.cache: Cache = cache if cache is not None else MemoryCache()
        self.cache_ttl = cache_ttl
        self.stale_ttl = max(stale_ttl, cache_ttl)
        self._locks: dict[str, asyncio.Lock] = {}

    async def stop_monitoring(self, station_id: str) -> StopMonitoring:
        """Réponse SIRI pour une gare (zone d'arrêt monomodale), via le cache."""
        key = f"stop-monitoring:{station_id}"

        entry = await self.cache.get(key)
        if entry and self._is_fresh(entry):
            return self._result(entry, "HIT")

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Une autre requête a peut-être rafraîchi l'entrée pendant l'attente
            entry = await self.cache.get(key)
            if entry and self._is_fresh(entry):
                return self._result(entry, "HIT")

            try:
                data = await self._fetch(station_id)
            except PrimConfigError:
                raise
            except PrimError:
                if entry:  # PRIM en panne : on sert la dernière donnée connue
                    return self._result(entry, "STALE")
                raise

            entry = {"fetched_at": time.time(), "data": data}
            await self.cache.set(key, entry, self.stale_ttl)
            return self._result(entry, "MISS")

    def _is_fresh(self, entry: dict) -> bool:
        return time.time() - entry["fetched_at"] < self.cache_ttl

    @staticmethod
    def _result(entry: dict, status: CacheStatus) -> StopMonitoring:
        fetched_at = datetime.fromtimestamp(entry["fetched_at"], timezone.utc)
        return StopMonitoring(data=entry["data"], fetched_at=fetched_at, cache=status)

    async def _fetch(self, station_id: str) -> dict:
        if not self.api_key:
            raise PrimConfigError("Clé API PRIM manquante (variable IDF_PRIM_API_KEY)")

        try:
            resp = await self.http.get(
                self.url,
                params={"MonitoringRef": f"STIF:StopArea:SP:{station_id}:"},
                headers={"apikey": self.api_key, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise PrimError(f"PRIM injoignable : {exc}") from exc
        if resp.status_code != 200:
            raise PrimError(f"PRIM a répondu {resp.status_code} : {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise PrimError("Réponse PRIM illisible (JSON invalide)") from exc


# --- Conversion SIRI -> modèle simplifié -------------------------------------------------


def _text(value: Any) -> str | None:
    """SIRI encode les textes en {"value": ...} ou [{"value": ...}]."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("value")
    return value or None


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _line_id(line_ref: str | None) -> str | None:
    # "STIF:Line::C01742:" -> "C01742"
    if not line_ref:
        return None
    parts = [p for p in line_ref.split(":") if p]
    return parts[-1] if parts else None


@dataclass
class StopVisit:
    """Passage d'un train à une gare, extrait de la réponse SIRI."""

    journey_ref: str | None
    line_id: str | None
    train_number: str | None
    destination: str
    direction: str | None
    mission: str | None
    platform: str | None
    aimed_arrival: datetime | None
    expected_arrival: datetime | None
    aimed_departure: datetime | None
    expected_departure: datetime | None
    departure_status: str | None
    arrival_status: str | None
    at_stop: bool

    @property
    def departure_time(self) -> datetime | None:
        return self.expected_departure or self.aimed_departure

    @property
    def arrival_time(self) -> datetime | None:
        """Heure de passage côté arrivée (au terminus, il n'y a pas d'heure de départ)."""
        return self.expected_arrival or self.aimed_arrival or self.departure_time

    @property
    def match_key(self) -> tuple | None:
        """Clé identifiant un même train d'une gare à l'autre."""
        if self.journey_ref:
            return ("journey", self.journey_ref)
        if self.train_number and self.line_id:
            return ("train", self.line_id, self.train_number)
        return None


def parse_visits(siri: dict) -> list[StopVisit]:
    deliveries = siri.get("Siri", {}).get("ServiceDelivery", {}).get("StopMonitoringDelivery", [])
    visits: list[StopVisit] = []
    for delivery in deliveries:
        for visit in delivery.get("MonitoredStopVisit", []):
            journey = visit.get("MonitoredVehicleJourney", {})
            call = journey.get("MonitoredCall", {})
            framed = journey.get("FramedVehicleJourneyRef") or {}
            train_numbers = (journey.get("TrainNumbers") or {}).get("TrainNumberRef", [])
            visits.append(
                StopVisit(
                    journey_ref=_text(framed.get("DatedVehicleJourneyRef")),
                    line_id=_line_id(_text(journey.get("LineRef"))),
                    train_number=_text(train_numbers),
                    destination=_text(call.get("DestinationDisplay"))
                    or _text(journey.get("DestinationName"))
                    or "?",
                    direction=_text(journey.get("DirectionName")),
                    mission=_text(journey.get("JourneyNote")),
                    platform=_text(call.get("DeparturePlatformName"))
                    or _text(call.get("ArrivalPlatformName")),
                    aimed_arrival=_dt(call.get("AimedArrivalTime")),
                    expected_arrival=_dt(call.get("ExpectedArrivalTime")),
                    aimed_departure=_dt(call.get("AimedDepartureTime")),
                    expected_departure=_dt(call.get("ExpectedDepartureTime")),
                    departure_status=call.get("DepartureStatus"),
                    arrival_status=call.get("ArrivalStatus"),
                    at_stop=bool(call.get("VehicleAtStop")),
                )
            )
    return visits


def resolve_line(repo: StationRepository, line_id: str | None) -> Line:
    line = repo.line(line_id) if line_id else None
    return line or Line(id=line_id or "?", name=line_id or "?", mode="?")


def _minutes(delta_seconds: float) -> int:
    return int(delta_seconds // 60)


def parse_departures(
    siri: dict, repo: StationRepository, now: datetime | None = None
) -> list[Departure]:
    now = now or datetime.now(timezone.utc)
    departures: list[Departure] = []
    for v in parse_visits(siri):
        expected = v.departure_time
        if expected is None:
            # Pas de départ : train qui arrive à son terminus
            continue
        # Trains déjà partis (on garde une petite marge pour ceux à quai)
        seconds = (expected - now).total_seconds()
        if seconds < -60:
            continue
        aimed = v.aimed_departure
        departures.append(
            Departure(
                line=resolve_line(repo, v.line_id),
                destination=v.destination,
                direction=v.direction,
                mission=v.mission,
                train_number=v.train_number,
                platform=v.platform,
                aimed_time=aimed,
                expected_time=expected,
                in_minutes=max(0, _minutes(seconds)),
                delay_minutes=_minutes((expected - aimed).total_seconds()) if aimed else 0,
                status=v.departure_status or "onTime",
                at_platform=v.at_stop,
            )
        )
    departures.sort(key=lambda d: d.expected_time)
    return departures
