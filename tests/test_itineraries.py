from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from idf_trains.main import app, get_navitia
from idf_trains.navitia import PARIS, NavitiaClient, parse_journey, parse_place

from navitia_fixtures import PLACES, journeys

BASE = datetime(2026, 11, 1, 16, 30)


def test_parse_place():
    places = [p for item in PLACES["places"] if (p := parse_place(item))]
    assert [p.type for p in places] == ["address", "stop_area", "poi"]  # « network » ignoré
    addr = places[0]
    assert addr.id == "2.3522;48.8566" and addr.city == "Paris"
    assert addr.lat == pytest.approx(48.8566) and addr.lon == pytest.approx(2.3522)
    assert places[2].city is None


def test_parse_journey():
    it = parse_journey(journeys(BASE)["journeys"][0])
    assert it.departure == datetime(2026, 11, 1, 16, 32, tzinfo=PARIS)
    assert it.departure.utcoffset().total_seconds() == 3600  # heure d'hiver
    assert (it.duration_minutes, it.transfers, it.walking_minutes, it.walking_distance_m) == (26, 0, 11, 850)
    assert it.status == "SIGNIFICANT_DELAYS" and it.co2_grams == 61.2
    # La section crow_fly de 0 s est ignorée
    assert [s.type for s in it.sections] == ["walk", "wait", "transit", "walk"]
    rer = it.sections[2]
    assert rer.line.code == "A" and rer.line.mode == "RER" and rer.line.color == "#E3051C"
    assert rer.delay_minutes == 2 and rer.headsign == "UPAC" and len(rer.stops) == 4
    assert it.sections[0].distance_m == 400 and it.sections[0].from_name == "12 Rue de Rivoli (Paris)"


def test_parse_journey_with_transfer():
    it = parse_journey(journeys(BASE)["journeys"][2])
    assert it.transfers == 1
    assert [s.type for s in it.sections] == ["walk", "transit", "transfer", "wait", "transit", "walk"]
    assert it.sections[4].line.code == "T2"


# --- API -----------------------------------------------------------------------------------


@pytest.fixture
def client():
    calls: list[httpx.Request] = []
    state = {"journeys": journeys(BASE), "status": 200}

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.path.endswith("/places"):
            return httpx.Response(200, json=PLACES)
        return httpx.Response(state["status"], json=state["journeys"])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    navitia = NavitiaClient(http, "key", "https://prim.test/navitia")
    app.dependency_overrides[get_navitia] = lambda: navitia
    with TestClient(app) as c:
        c.calls, c.state = calls, state
        yield c
    app.dependency_overrides.clear()


def test_places_endpoint(client):
    resp = client.get("/places", params={"q": "12 rue de Rivoli"})
    assert resp.status_code == 200
    assert [p["type"] for p in resp.json()] == ["address", "stop_area", "poi"]
    req = client.calls[0]
    assert req.headers["apikey"] == "key"
    assert req.url.params["q"] == "12 rue de rivoli"
    assert req.url.params.get_list("type[]") == ["address", "stop_area", "poi", "administrative_region"]

    # Même recherche (casse/espaces différents) : servie depuis le cache
    client.get("/places", params={"q": "12  Rue de RIVOLI"})
    assert len(client.calls) == 1

    assert client.get("/places", params={"q": "ab"}).status_code == 422


def test_itineraries_endpoint(client):
    resp = client.get(
        "/itineraries",
        params={"from": "2.3522;48.8566", "to": "stop_area:IDFM:71517", "datetime": "2026-11-01T16:30", "represents": "arrival"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["itineraries"]) == 3 and body["message"] is None
    assert body["itineraries"][0]["departure"] == "2026-11-01T16:32:00+01:00"

    params = client.calls[0].url.params
    assert params["from"] == "2.3522;48.8566" and params["to"] == "stop_area:IDFM:71517"
    assert params["datetime"] == "20261101T163000" and params["datetime_represents"] == "arrival"


def test_itineraries_converts_utc_to_paris_time(client):
    client.get("/itineraries", params={"from": "a:1", "to": "b:2", "datetime": "2026-11-01T15:30:00Z"})
    assert client.calls[0].url.params["datetime"] == "20261101T163000"


def test_itineraries_without_datetime_means_now(client):
    client.get("/itineraries", params={"from": "a:1", "to": "b:2"})
    assert "datetime" not in client.calls[0].url.params


def test_itineraries_no_solution(client):
    client.state.update(status=404, journeys={"error": {"id": "no_solution", "message": "no solution found"}})
    body = client.get("/itineraries", params={"from": "a:1", "to": "b:2"}).json()
    assert body["itineraries"] == [] and body["message"] == "Aucun itinéraire trouvé."


@pytest.mark.parametrize(
    "error_id, status",
    [("unknown_object", 422), ("date_out_of_bounds", 422), ("internal_error", 502)],
)
def test_itineraries_navitia_errors(client, error_id, status):
    client.state.update(status=404, journeys={"error": {"id": error_id, "message": "x"}})
    assert client.get("/itineraries", params={"from": "a:1", "to": "b:2"}).status_code == status


def test_itineraries_quota_and_auth(client):
    client.state.update(status=429, journeys={"message": "Too Many Requests"})
    assert client.get("/itineraries", params={"from": "a:1", "to": "b:2"}).status_code == 429
    client.state.update(status=401, journeys={"message": "Unauthorized"})
    assert client.get("/itineraries", params={"from": "a:1", "to": "c:3"}).status_code == 502


def test_itineraries_validation(client):
    assert client.get("/itineraries", params={"from": "a:1", "to": "a:1"}).status_code == 422
    assert client.get("/itineraries", params={"from": "a b<script>", "to": "b:2"}).status_code == 422
    assert client.get("/itineraries", params={"from": "a:1", "to": "b:2", "represents": "x"}).status_code == 422
    assert client.calls == []


def test_missing_api_key():
    navitia = NavitiaClient(httpx.AsyncClient(), "", "https://prim.test/navitia")
    app.dependency_overrides[get_navitia] = lambda: navitia
    try:
        with TestClient(app) as c:
            assert c.get("/itineraries", params={"from": "a:1", "to": "b:2"}).status_code == 503
    finally:
        app.dependency_overrides.clear()
