from datetime import datetime

from pydantic import BaseModel


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
