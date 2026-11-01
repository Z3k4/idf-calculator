"""Recherche des trains directs entre deux gares.

Principe : on interroge les prochains passages (SIRI StopMonitoring) aux deux gares. Un train
est retenu s'il apparaît aux deux (même identifiant de course, ou à défaut même ligne + numéro
de train) et s'il passe à la gare d'arrivée *après* la gare de départ : il dessert donc bien la
gare d'arrivée, dans le bon sens.

Limite : la gare d'arrivée n'annonce que ses prochains passages (horizon d'environ 1 à 2 h) ;
un trajet très long peut donc ne pas être détecté tant que le train n'approche pas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import JourneyTrain, Line, Station
from .prim import StopVisit, resolve_line
from .stations import StationRepository

# Au-delà, l'appariement est jugé incohérent (ex. même train le lendemain)
MAX_TRIP_DURATION = timedelta(hours=4)


def common_lines(origin: Station, destination: Station) -> list[Line]:
    dest_ids = {l.id for l in destination.lines}
    return [l for l in origin.lines if l.id in dest_ids]


def find_direct_trains(
    origin_visits: list[StopVisit],
    destination_visits: list[StopVisit],
    repo: StationRepository,
    now: datetime | None = None,
) -> list[JourneyTrain]:
    now = now or datetime.now(timezone.utc)

    at_destination: dict[tuple, list[StopVisit]] = {}
    for v in destination_visits:
        if v.match_key and v.arrival_time:
            at_destination.setdefault(v.match_key, []).append(v)

    trains: list[JourneyTrain] = []
    for dep in origin_visits:
        dep_time = dep.departure_time
        if dep.match_key is None or dep_time is None:
            continue
        seconds = (dep_time - now).total_seconds()
        if seconds < -60:
            continue

        # Premier passage du même train à l'arrivée, après le départ
        candidates = [
            a
            for a in at_destination.get(dep.match_key, [])
            if timedelta(0) < a.arrival_time - dep_time <= MAX_TRIP_DURATION
        ]
        if not candidates:
            continue
        arr = min(candidates, key=lambda a: a.arrival_time)
        arr_time = arr.arrival_time

        cancelled = "cancelled" in (dep.departure_status, arr.arrival_status)
        trains.append(
            JourneyTrain(
                line=resolve_line(repo, dep.line_id),
                destination=dep.destination,
                mission=dep.mission,
                train_number=dep.train_number,
                platform=dep.platform,
                aimed_departure=dep.aimed_departure,
                expected_departure=dep_time,
                aimed_arrival=arr.aimed_arrival or arr.aimed_departure,
                expected_arrival=arr_time,
                in_minutes=max(0, int(seconds // 60)),
                duration_minutes=int((arr_time - dep_time).total_seconds() // 60),
                delay_minutes=int((dep_time - dep.aimed_departure).total_seconds() // 60)
                if dep.aimed_departure
                else 0,
                status="cancelled" if cancelled else dep.departure_status or "onTime",
                at_platform=dep.at_stop,
            )
        )

    trains.sort(key=lambda t: t.expected_departure)
    return trains
