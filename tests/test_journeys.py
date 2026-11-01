from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from idf_trains.config import settings
from idf_trains.journeys import find_direct_trains
from idf_trains.main import app, get_prim, get_repo, get_store
from idf_trains.prim import PrimClient, parse_visits
from idf_trains.stations import StationRepository
from idf_trains.storage import DuplicateJourneyError, JourneyStore

CHATELET, GARE_DE_LYON, LA_DEFENSE = "45102", "470195", "470549"
RER_A, RER_D = "C01742", "C01728"


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def visit(journey, line, dest, dep=None, arr=None, train=None, status="onTime", journey_ref=True):
    call = {"DestinationDisplay": [{"value": dest}], "DepartureStatus": status}
    if dep is not None:
        call["AimedDepartureTime"] = call["ExpectedDepartureTime"] = iso(dep)
    if arr is not None:
        call["AimedArrivalTime"] = call["ExpectedArrivalTime"] = iso(arr)
    mvj = {"LineRef": {"value": f"STIF:Line::{line}:"}, "MonitoredCall": call}
    if journey_ref:
        mvj["FramedVehicleJourneyRef"] = {"DatedVehicleJourneyRef": journey}
    if train:
        mvj["TrainNumbers"] = {"TrainNumberRef": [{"value": train}]}
    return {"MonitoredVehicleJourney": mvj}


def siri(*visits):
    return {"Siri": {"ServiceDelivery": {"StopMonitoringDelivery": [{"MonitoredStopVisit": list(visits)}]}}}


@pytest.fixture(scope="module")
def repo():
    return StationRepository.from_file(settings.stations_file)


# --- Appariement des trains ----------------------------------------------------------------


def test_find_direct_trains(repo):
    t0 = now()
    m = lambda n: t0 + timedelta(minutes=n)
    at_origin = siri(
        visit("J1", RER_A, "Boissy", dep=m(2)),  # vers l'est : passe à Gare de Lyon après
        visit("J2", RER_A, "Cergy", dep=m(4)),  # vers l'ouest : ne passe pas à Gare de Lyon
        visit("J3", RER_D, "Melun", dep=m(6)),
        visit("J4", RER_A, "Chessy", dep=m(9)),
        visit("J5", RER_A, "Chessy", dep=m(-10)),  # déjà parti
    )
    at_dest = siri(
        visit("J1", RER_A, "Boissy", dep=m(4), arr=m(4)),
        visit("J3", RER_D, "Melun", dep=m(9), arr=m(8), status="delayed"),
        visit("J4", RER_A, "Chessy", dep=m(-1), arr=m(-1)),  # passé à l'arrivée AVANT le départ
        visit("J5", RER_A, "Chessy", dep=m(-8), arr=m(-8)),
    )
    trains = find_direct_trains(parse_visits(at_origin), parse_visits(at_dest), repo, now=t0)
    assert [(t.line.name, t.destination) for t in trains] == [("A", "Boissy"), ("D", "Melun")]
    assert trains[0].duration_minutes == 2 and trains[0].in_minutes in (1, 2)
    assert trains[1].duration_minutes == 2  # heure d'arrivée prise en priorité


def test_match_by_train_number_without_journey_ref(repo):
    t0 = now()
    origin = siri(visit(None, RER_D, "Melun", dep=t0 + timedelta(minutes=5), train="123", journey_ref=False))
    dest = siri(visit(None, RER_D, "Melun", arr=t0 + timedelta(minutes=12), train="123", journey_ref=False))
    trains = find_direct_trains(parse_visits(origin), parse_visits(dest), repo, now=t0)
    assert len(trains) == 1 and trains[0].duration_minutes == 7


def test_cancelled_at_destination_marks_train_cancelled(repo):
    t0 = now()
    origin = siri(visit("J1", RER_A, "Boissy", dep=t0 + timedelta(minutes=3)))
    dest = siri(visit("J1", RER_A, "Boissy", arr=t0 + timedelta(minutes=6), status="cancelled"))
    dest["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"][0][
        "MonitoredVehicleJourney"
    ]["MonitoredCall"]["ArrivalStatus"] = "cancelled"
    trains = find_direct_trains(parse_visits(origin), parse_visits(dest), repo, now=t0)
    assert trains[0].status == "cancelled"


# --- Stockage ------------------------------------------------------------------------------


def test_store_crud(tmp_path):
    store = JourneyStore(tmp_path / "j.db")
    row = store.create(CHATELET, GARE_DE_LYON, "Boulot")
    assert store.get(row.id).name == "Boulot"
    with pytest.raises(DuplicateJourneyError):
        store.create(CHATELET, GARE_DE_LYON, None)
    store.create(GARE_DE_LYON, CHATELET, None)  # sens inverse = autre trajet
    assert len(store.list()) == 2
    assert store.rename(row.id, "Maison").name == "Maison"
    assert store.delete(row.id) and store.get(row.id) is None
    assert not store.delete(row.id)


# --- API -----------------------------------------------------------------------------------


@pytest.fixture
def client(repo, tmp_path):
    t0 = now()
    by_station = {
        CHATELET: siri(
            visit("J1", RER_A, "Boissy", dep=t0 + timedelta(minutes=3)),
            visit("J2", RER_D, "Melun", dep=t0 + timedelta(minutes=5)),
        ),
        GARE_DE_LYON: siri(
            visit("J1", RER_A, "Boissy", arr=t0 + timedelta(minutes=5), dep=t0 + timedelta(minutes=6)),
            visit("J2", RER_D, "Melun", arr=t0 + timedelta(minutes=8)),
        ),
    }
    calls = []

    def handler(request: httpx.Request):
        ref = request.url.params["MonitoringRef"]  # STIF:StopArea:SP:45102:
        station_id = ref.split(":")[-2]
        calls.append(station_id)
        return httpx.Response(200, json=by_station.get(station_id, siri()))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    prim = PrimClient(http, "key", "https://prim.test", cache_ttl=30)
    store = JourneyStore(tmp_path / "journeys.db")
    app.dependency_overrides.update({get_repo: lambda: repo, get_prim: lambda: prim, get_store: lambda: store})
    with TestClient(app) as c:
        c.calls = calls
        yield c
    app.dependency_overrides.clear()


def test_next_trains_endpoint(client):
    resp = client.get("/journeys/next", params={"from": CHATELET, "to": GARE_DE_LYON})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["origin"]["id"] == CHATELET and body["destination"]["id"] == GARE_DE_LYON
    assert {l["name"] for l in body["common_lines"]} == {"A", "D"}
    assert [(t["line"]["name"], t["duration_minutes"]) for t in body["trains"]] == [("A", 2), ("D", 3)]
    assert sorted(client.calls) == sorted([CHATELET, GARE_DE_LYON])

    resp = client.get("/journeys/next", params={"from": CHATELET, "to": GARE_DE_LYON, "line": "D"})
    assert [t["line"]["name"] for t in resp.json()["trains"]] == ["D"]


def test_next_trains_no_common_line(client):
    # La Défense (A, E, L, U) -> Gare du Nord (B, D, H, K, TER) : pas de ligne directe
    resp = client.get("/journeys/next", params={"from": LA_DEFENSE, "to": "462394"})
    body = resp.json()
    assert resp.status_code == 200 and body["trains"] == [] and body["common_lines"] == []
    assert body["message"] and client.calls == []  # PRIM non appelé


def test_next_trains_errors(client):
    assert client.get("/journeys/next", params={"from": CHATELET, "to": CHATELET}).status_code == 422
    assert client.get("/journeys/next", params={"from": "000", "to": CHATELET}).status_code == 404
    assert client.get("/journeys/next", params={"from": CHATELET}).status_code == 422


def test_saved_journeys_crud(client):
    assert client.get("/journeys").json() == []

    resp = client.post("/journeys", json={"origin_id": CHATELET, "destination_id": GARE_DE_LYON, "name": "  Boulot "})
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved["name"] == "Boulot" and saved["origin"]["name"] == "Châtelet - Les Halles"
    jid = saved["id"]

    assert client.post("/journeys", json={"origin_id": CHATELET, "destination_id": GARE_DE_LYON}).status_code == 409
    assert client.post("/journeys", json={"origin_id": LA_DEFENSE, "destination_id": "462394"}).status_code == 422
    assert client.post("/journeys", json={"origin_id": "000", "destination_id": CHATELET}).status_code == 404

    assert [j["id"] for j in client.get("/journeys").json()] == [jid]
    assert client.get(f"/journeys/{jid}").json()["name"] == "Boulot"

    nxt = client.get(f"/journeys/{jid}/next").json()
    assert nxt["trains"][0]["line"]["name"] == "A"

    assert client.patch(f"/journeys/{jid}", json={"name": "Travail"}).json()["name"] == "Travail"
    assert client.patch(f"/journeys/{jid}", json={"name": ""}).json()["name"] is None

    assert client.delete(f"/journeys/{jid}").status_code == 204
    assert client.get(f"/journeys/{jid}").status_code == 404
    assert client.delete(f"/journeys/{jid}").status_code == 404
