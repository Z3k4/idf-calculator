from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Line(BaseModel):
    id: str
    name: str
    mode: str


class Station(BaseModel):
    id: str
    name: str
    city: str
    lat: float
    lon: float
    lines: list[Line]


class StationMatch(BaseModel):
    score: float
    station: Station


class Departure(BaseModel):
    line: Line
    destination: str
    direction: str | None = None
    mission: str | None = None
    train_number: str | None = None
    platform: str | None = None
    aimed_time: datetime | None = None
    expected_time: datetime
    in_minutes: int
    delay_minutes: int
    status: str
    at_platform: bool = False


class DeparturesResponse(BaseModel):
    station: Station
    # Date de la donnée temps réel (peut dater de quelques secondes si servie depuis le cache)
    updated_at: datetime
    # True si PRIM est indisponible et que la dernière donnée connue est renvoyée
    stale: bool = False
    departures: list[Departure]


# --- Trajets (gare de départ -> gare d'arrivée) ------------------------------------------


class JourneyTrain(BaseModel):
    """Un train direct qui part de la gare de départ et dessert la gare d'arrivée."""

    line: Line
    destination: str
    mission: str | None = None
    train_number: str | None = None
    platform: str | None = None
    aimed_departure: datetime | None = None
    expected_departure: datetime
    aimed_arrival: datetime | None = None
    expected_arrival: datetime
    in_minutes: int
    duration_minutes: int
    delay_minutes: int
    status: str
    at_platform: bool = False


class JourneyNextResponse(BaseModel):
    origin: Station
    destination: Station
    # Lignes communes aux deux gares (vide = aucun train direct possible)
    common_lines: list[Line]
    updated_at: datetime
    stale: bool = False
    trains: list[JourneyTrain]
    message: str | None = None


class SavedJourneyCreate(BaseModel):
    origin_id: str
    destination_id: str
    name: str | None = Field(None, max_length=80)


class SavedJourneyUpdate(BaseModel):
    name: str | None = Field(None, max_length=80)


class SavedJourney(BaseModel):
    id: int
    name: str | None
    origin: Station
    destination: Station
    common_lines: list[Line]
    created_at: datetime


# --- Itinéraires (calculateur Navitia IDFM) ----------------------------------------------


class Place(BaseModel):
    """Lieu utilisable comme départ/arrivée : adresse, arrêt, point d'intérêt, commune."""

    # Identifiant Navitia (ex. « stop_area:IDFM:71517 ») ou coordonnées « lon;lat » pour une adresse
    id: str
    name: str
    type: str
    city: str | None = None
    lat: float | None = None
    lon: float | None = None


class TransitLine(BaseModel):
    code: str
    name: str | None = None
    mode: str
    network: str | None = None
    color: str | None = None
    text_color: str | None = None


class ItinerarySection(BaseModel):
    # walk : marche · transit : transport en commun · transfer : correspondance à pied · wait : attente
    type: str
    departure: datetime | None = None
    arrival: datetime | None = None
    duration_minutes: int
    from_name: str | None = None
    to_name: str | None = None
    line: TransitLine | None = None
    direction: str | None = None
    headsign: str | None = None
    stops: list[str] = []
    delay_minutes: int = 0
    distance_m: int | None = None
    # Tracé [[lon, lat], …] pour un affichage cartographique
    geometry: list[list[float]] = []


class Itinerary(BaseModel):
    departure: datetime
    arrival: datetime
    duration_minutes: int
    transfers: int
    walking_minutes: int
    walking_distance_m: int | None = None
    co2_grams: float | None = None
    tags: list[str] = []
    status: str | None = None
    sections: list[ItinerarySection]


class ItinerariesResponse(BaseModel):
    origin: str
    destination: str
    itineraries: list[Itinerary]
    message: str | None = None


class PlaceInput(BaseModel):
    """Lieu tel que renvoyé par /places, envoyé par le client pour sauvegarder un itinéraire."""

    id: str = Field(..., pattern=r"^[\w:;.\-]{1,200}$")
    name: str = Field(..., min_length=1, max_length=200)
    type: Literal["address", "stop_area", "poi", "administrative_region"]
    city: str | None = Field(None, max_length=120)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class SavedItineraryCreate(BaseModel):
    origin: PlaceInput
    destination: PlaceInput
    name: str | None = Field(None, max_length=80)


class SavedItinerary(BaseModel):
    id: int
    name: str | None
    origin: Place
    destination: Place
    created_at: datetime


# --- Suivi de consommation des API IDFM --------------------------------------------------


class ApiUsageToday(BaseModel):
    api: str
    label: str
    calls: int
    errors: int
    # Requêtes servies par le cache, sans appel à IDFM
    cache_hits: int
    quota: int | None = None
    remaining: int | None = None


class UsageDay(BaseModel):
    day: str
    api: str
    calls: int
    errors: int
    cache_hits: int


class UsageHour(BaseModel):
    hour: int
    api: str
    calls: int


class UsageEndpoint(BaseModel):
    api: str
    endpoint: str
    calls: int
    errors: int
    avg_ms: int


class UsageCall(BaseModel):
    at: datetime
    api: str
    endpoint: str
    status: int
    duration_ms: int


class UsageResponse(BaseModel):
    day: str
    timezone: str = "Europe/Paris"
    apis: list[ApiUsageToday]
    daily: list[UsageDay]
    hourly: list[UsageHour]
    endpoints: list[UsageEndpoint]
    recent: list[UsageCall]


# --- Page d'accueil ------------------------------------------------------------------------


class HomeItemRef(BaseModel):
    kind: Literal["journey", "itinerary"]
    id: int


class HomeUpdate(BaseModel):
    items: list[HomeItemRef] = Field(..., max_length=20)


class HomeItem(BaseModel):
    kind: Literal["journey", "itinerary"]
    id: int
    journey: SavedJourney | None = None
    itinerary: SavedItinerary | None = None


class HomeResponse(BaseModel):
    items: list[HomeItem]
