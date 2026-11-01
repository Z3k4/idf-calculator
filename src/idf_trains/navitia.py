"""Client du calculateur d'itinéraires IDFM (API Navitia exposée par PRIM) et conversion simplifiée.

Référence du format : https://doc.navitia.io (endpoints /places et /journeys).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .cache import Cache, MemoryCache
from .models import Itinerary, ItinerarySection, Place, TransitLine
from .prim import PrimConfigError, PrimError

PARIS = ZoneInfo("Europe/Paris")
NAVITIA_DT = "%Y%m%dT%H%M%S"

# Identifiant Navitia (stop_area:IDFM:71517, admin:fr:75056…) ou coordonnées « lon;lat »
PLACE_ID = re.compile(r"^[\w:;.\-]{1,200}$")

PLACE_TYPES = ("address", "stop_area", "poi", "administrative_region")


class NavitiaError(PrimError):
    def __init__(self, message: str, status: int = 502, error_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.error_id = error_id


class NoSolution(NavitiaError):
    """Aucun itinéraire trouvé (réponse normale, pas une panne)."""


class NavitiaClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        base_url: str,
        cache: Cache | None = None,
        places_ttl: float = 86400.0,
        journeys_ttl: float = 60.0,
    ):
        self.http = http
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cache: Cache = cache if cache is not None else MemoryCache()
        self.places_ttl = places_ttl
        self.journeys_ttl = journeys_ttl

    async def _get(self, path: str, params: list[tuple[str, str]], cache_key: str, ttl: float) -> dict:
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached
        if not self.api_key:
            raise PrimConfigError("Clé API PRIM manquante (variable IDF_PRIM_API_KEY)")

        try:
            resp = await self.http.get(
                f"{self.base_url}/{path}",
                params=params,
                headers={"apikey": self.api_key, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise NavitiaError(f"Calculateur IDFM injoignable : {exc}") from exc

        try:
            data = resp.json()
        except ValueError:
            data = {}

        error = data.get("error") if isinstance(data, dict) else None
        if error:
            raise _error(error)
        if resp.status_code == 429:
            raise NavitiaError("Quota de l'API IDFM dépassé, réessayez plus tard", status=429)
        if resp.status_code in (401, 403):
            raise NavitiaError("Clé API refusée par le calculateur IDFM (abonnement à l'API ?)")
        if resp.status_code != 200:
            raise NavitiaError(f"Le calculateur IDFM a répondu {resp.status_code}")

        await self.cache.set(cache_key, data, ttl)
        return data

    async def places(self, query: str, count: int = 8) -> list[Place]:
        q = " ".join(query.lower().split())
        params = [("q", q), ("count", str(count))] + [("type[]", t) for t in PLACE_TYPES]
        data = await self._get("places", params, f"navitia:places:{count}:{q}", self.places_ttl)
        return [p for item in data.get("places", []) if (p := parse_place(item))]

    async def journeys(
        self,
        origin: str,
        destination: str,
        when: datetime | None = None,
        represents: str = "departure",
        count: int = 3,
    ) -> list[Itinerary]:
        params = [
            ("from", origin),
            ("to", destination),
            ("count", str(count)),
            ("data_freshness", "realtime"),
        ]
        if when is not None:
            local = when.astimezone(PARIS) if when.tzinfo else when
            params += [("datetime", local.strftime(NAVITIA_DT)), ("datetime_represents", represents)]
        key = "navitia:journeys:" + "&".join(f"{k}={v}" for k, v in params)
        data = await self._get("journeys", params, key, self.journeys_ttl)
        return [parse_journey(j) for j in data.get("journeys", [])]


def _error(error: dict) -> NavitiaError:
    error_id = error.get("id")
    if error_id == "no_solution":
        return NoSolution("Aucun itinéraire trouvé.", status=200, error_id=error_id)
    if error_id == "date_out_of_bounds":
        return NavitiaError(
            "Date hors de la période couverte par le calculateur", status=422, error_id=error_id
        )
    if error_id in ("unknown_object", "no_origin", "no_destination", "no_origin_nor_destination"):
        return NavitiaError("Lieu de départ ou d'arrivée introuvable", status=422, error_id=error_id)
    return NavitiaError(f"Erreur du calculateur IDFM : {error.get('message', error_id)}", error_id=error_id)


# --- Conversion ----------------------------------------------------------------------------


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, NAVITIA_DT).replace(tzinfo=PARIS)


def _minutes(seconds: Any) -> int:
    return round((seconds or 0) / 60)


def _coord(obj: dict) -> tuple[float | None, float | None]:
    coord = obj.get("coord") or {}
    try:
        return float(coord["lat"]), float(coord["lon"])
    except (KeyError, TypeError, ValueError):
        return None, None


def _city(obj: dict) -> str | None:
    regions = obj.get("administrative_regions") or []
    # Niveau 8 = commune
    for region in regions:
        if region.get("level") == 8:
            return region.get("name")
    return regions[0].get("name") if regions else None


def parse_place(item: dict) -> Place | None:
    kind = item.get("embedded_type")
    if not item.get("id") or kind not in PLACE_TYPES:
        return None
    obj = item.get(kind) or {}
    lat, lon = _coord(obj)
    return Place(
        id=item["id"],
        name=item.get("name") or obj.get("label") or item["id"],
        type=kind,
        city=_city(obj),
        lat=lat,
        lon=lon,
    )


SECTION_TYPES = {
    "public_transport": "transit",
    "on_demand_transport": "transit",
    "street_network": "walk",
    "crow_fly": "walk",
    "transfer": "transfer",
    "waiting": "wait",
}


def _color(value: str | None) -> str | None:
    return f"#{value}" if value and re.fullmatch(r"[0-9A-Fa-f]{6}", value) else None


def _length(section: dict) -> int | None:
    """Longueur en mètres, dans geojson.properties[0].length."""
    props = (section.get("geojson") or {}).get("properties") or []
    length = props[0].get("length") if props and isinstance(props[0], dict) else None
    return int(length) if isinstance(length, (int, float)) else None


def parse_section(section: dict) -> ItinerarySection | None:
    kind = SECTION_TYPES.get(section.get("type", ""))
    if kind is None:
        return None
    duration = section.get("duration") or 0
    # Navitia ajoute des sections « crow_fly » de 0 s quand le départ est déjà un arrêt
    if kind == "walk" and duration == 0:
        return None

    departure = _dt(section.get("departure_date_time"))
    arrival = _dt(section.get("arrival_date_time"))
    line = None
    direction = headsign = None
    stops: list[str] = []
    delay = 0
    if kind == "transit":
        info = section.get("display_informations") or {}
        line = TransitLine(
            code=info.get("code") or info.get("label") or "?",
            name=info.get("name"),
            mode=info.get("commercial_mode") or info.get("physical_mode") or "?",
            network=info.get("network"),
            color=_color(info.get("color")),
            text_color=_color(info.get("text_color")),
        )
        direction = info.get("direction")
        headsign = info.get("headsign") or None
        stops = [
            (sdt.get("stop_point") or {}).get("name", "?") for sdt in section.get("stop_date_times") or []
        ]
        base = _dt(section.get("base_departure_date_time"))
        if base and departure:
            delay = round((departure - base).total_seconds() / 60)

    return ItinerarySection(
        type=kind,
        departure=departure,
        arrival=arrival,
        duration_minutes=_minutes(duration),
        from_name=(section.get("from") or {}).get("name"),
        to_name=(section.get("to") or {}).get("name"),
        line=line,
        direction=direction,
        headsign=headsign,
        stops=stops,
        delay_minutes=delay,
        distance_m=_length(section) if kind in ("walk", "transfer") else None,
        geometry=(section.get("geojson") or {}).get("coordinates") or [],
    )


def parse_journey(journey: dict) -> Itinerary:
    durations = journey.get("durations") or {}
    distances = journey.get("distances") or {}
    co2 = journey.get("co2_emission") or {}
    return Itinerary(
        departure=_dt(journey["departure_date_time"]),
        arrival=_dt(journey["arrival_date_time"]),
        duration_minutes=_minutes(journey.get("duration")),
        transfers=journey.get("nb_transfers") or 0,
        walking_minutes=_minutes(durations.get("walking")),
        walking_distance_m=distances.get("walking"),
        co2_grams=co2.get("value"),
        tags=journey.get("tags") or [],
        status=journey.get("status") or None,
        sections=[s for sec in journey.get("sections") or [] if (s := parse_section(sec))],
    )
