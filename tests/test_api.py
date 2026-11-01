from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from idf_trains.config import settings
from idf_trains.main import app, get_prim, get_repo
from idf_trains.prim import PrimClient, parse_departures
from idf_trains.stations import StationRepository, normalize

NOW = datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc)


def iso(minutes: float) -> str:
    return (NOW + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def visit(line="C01742", dest="Cergy le Haut", aimed=5, expected=5, **call_extra):
    call = {
        "AimedDepartureTime": iso(aimed),
        "ExpectedDepartureTime": iso(expected),
        "DestinationDisplay": [{"value": dest}],
        "DepartureStatus": "onTime",
        "ArrivalPlatformName": {"value": "A"},
        **call_extra,
    }
    return {
        "MonitoredVehicleJourney": {
            "LineRef": {"value": f"STIF:Line::{line}:"},
            "DestinationName": [{"value": dest}],
            "DirectionName": [{"value": dest}],
            "JourneyNote": [{"value": "QIKI"}],
            "TrainNumbers": {"TrainNumberRef": [{"value": "123456"}]},
            "MonitoredCall": call,
        }
    }


def siri(*visits):
    return {
        "Siri": {
            "ServiceDelivery": {"StopMonitoringDelivery": [{"MonitoredStopVisit": list(visits)}]}
        }
    }


@pytest.fixture(scope="module")
def repo():
    return StationRepository.from_file(settings.stations_file)


def test_normalize():
    assert normalize("Châtelet - Les Halles") == "chatelet les halles"


def test_search_accent_insensitive(repo):
    results = repo.search("chatelet")
    assert results[0].name == "Châtelet - Les Halles"
    assert {l.name for l in results[0].lines} >= {"A", "B", "D"}


def test_search_by_line(repo):
    results = repo.search("", line="A", limit=500)
    assert results and all(any(l.name == "A" for l in s.lines) for s in results)


def test_parse_departures(repo):
    data = siri(
        visit(dest="Marne-la-Vallée", aimed=10, expected=12),
        visit(dest="Cergy le Haut", aimed=3, expected=3),
        visit(dest="Déjà parti", aimed=-5, expected=-5),
        visit(line="C01728", dest="Melun", aimed=7, expected=7, DepartureStatus="cancelled"),
    )
    deps = parse_departures(data, repo, now=NOW)
    assert [d.destination for d in deps] == ["Cergy le Haut", "Melun", "Marne-la-Vallée"]
    first, cancelled, delayed = deps
    assert first.line.name == "A" and first.line.mode == "RER"
    assert first.in_minutes == 3 and first.mission == "QIKI" and first.platform == "A"
    assert cancelled.line.name == "D" and cancelled.status == "cancelled"
    assert delayed.delay_minutes == 2


def test_parse_skips_terminus_arrivals(repo):
    v = visit()
    call = v["MonitoredVehicleJourney"]["MonitoredCall"]
    del call["AimedDepartureTime"], call["ExpectedDepartureTime"]
    call["ExpectedArrivalTime"] = iso(4)
    assert parse_departures(siri(v), repo, now=NOW) == []


@pytest.fixture
def client(repo):
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json=siri(visit(aimed=3, expected=3), visit(line="C01728", dest="Melun")))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    prim = PrimClient(http, "test-key", "https://prim.test/stop-monitoring", cache_ttl=30)
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_prim] = lambda: prim
    with TestClient(app) as c:
        c.requests = requests
        yield c
    app.dependency_overrides.clear()


def test_departures_endpoint(client):
    # Les horaires du mock sont relatifs à NOW (passé) : on vérifie surtout la requête PRIM
    resp = client.get("/stations/45102/departures")
    assert resp.status_code == 200
    body = resp.json()
    assert body["station"]["name"] == "Châtelet - Les Halles"
    assert body["stale"] is False
    assert resp.headers["X-Cache"] == "MISS"
    req = client.requests[0]
    assert req.url.params["MonitoringRef"] == "STIF:StopArea:SP:45102:"
    assert req.headers["apikey"] == "test-key"

    resp = client.get("/stations/45102/departures")
    assert len(client.requests) == 1  # cache
    assert resp.headers["X-Cache"] == "HIT"
    assert resp.headers["Cache-Control"].startswith("public, max-age=")


def test_unknown_station(client):
    assert client.get("/stations/000/departures").status_code == 404


def test_search_endpoint(client):
    resp = client.get("/stations", params={"q": "gare de lyon"})
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "470195"
