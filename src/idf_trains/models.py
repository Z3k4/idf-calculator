from datetime import datetime

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
