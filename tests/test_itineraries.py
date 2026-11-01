from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from idf_trains.main import app, get_itinerary_store, get_navitia
from idf_trains.navitia import PARIS, NavitiaClient, parse_journey, parse_place
from idf_trains.storage import ItineraryStore, PlaceSearchStore

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
def client(tmp_path):
    calls: list[httpx.Request] = []
    state = {"journeys": journeys(BASE), "status": 200}

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.path.endswith("/places"):
            return httpx.Response(200, json=PLACES)
        return httpx.Response(state["status"], json=state["journeys"])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    navitia = NavitiaClient(http, "key", "https://prim.test/navitia")
    store = ItineraryStore(tmp_path / "it.db")
    app.dependency_overrides[get_navitia] = lambda: navitia
    app.dependency_overrides[get_itinerary_store] = lambda: store
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


# --- Cache persistant des adresses -------------------------------------------------------


def test_place_search_store(tmp_path, monkeypatch):
    store = PlaceSearchStore(tmp_path / "p.db", max_age=100)
    assert store.get("rivoli") is None
    store.set("rivoli", [{"id": "1;2", "name": "Rivoli"}])
    assert store.get("rivoli") == [{"id": "1;2", "name": "Rivoli"}]

    import idf_trains.storage as storage

    now = storage._now()
    monkeypatch.setattr(storage, "_now", lambda: now + 101)  # expiré
    assert store.get("rivoli") is None
    assert store.purge() == 1


def test_places_persistent_cache_survives_restart(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=PLACES)

    import asyncio

    async def scenario():
        db = tmp_path / "places.db"
        first = NavitiaClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "key", "https://x", place_store=PlaceSearchStore(db))
        a = await first.places("12 Rue de Rivoli")
        # Nouveau client = nouveau cache mémoire (comme après un redémarrage), même base SQLite
        second = NavitiaClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "key", "https://x", place_store=PlaceSearchStore(db))
        b = await second.places("12  rue de RIVOLI")
        return a, b

    a, b = asyncio.run(scenario())
    assert len(calls) == 1
    assert [p.id for p in a] == [p.id for p in b] and b[0].city == "Paris"


# --- Itinéraires sauvegardés -------------------------------------------------------------

RIVOLI = {"id": "2.3522;48.8566", "name": "12 Rue de Rivoli (Paris)", "type": "address", "city": "Paris", "lat": 48.8566, "lon": 2.3522}
GDL = {"id": "stop_area:IDFM:71517", "name": "Gare de Lyon (Paris)", "type": "stop_area", "city": "Paris"}


def test_saved_itineraries_crud(client):
    assert client.get("/itineraries/saved").json() == []

    resp = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "name": " Boulot "})
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved["name"] == "Boulot" and saved["origin"]["lat"] == 48.8566
    assert saved["destination"]["type"] == "stop_area"
    sid = saved["id"]

    assert client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL}).status_code == 409
    # Mêmes lieux avec un autre horaire : nouvel itinéraire
    morning = {"mode": "departure", "time": "08:00"}
    resp = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "schedule": morning})
    assert resp.status_code == 201, resp.text
    client.delete(f"/itineraries/saved/{resp.json()['id']}")
    # Sens inverse : autre itinéraire
    assert client.post("/itineraries/saved", json={"origin": GDL, "destination": RIVOLI}).status_code == 201
    assert len(client.get("/itineraries/saved").json()) == 2

    assert client.get(f"/itineraries/saved/{sid}").json()["origin"]["name"] == RIVOLI["name"]
    assert client.patch(f"/itineraries/saved/{sid}", json={"name": "Travail"}).json()["name"] == "Travail"

    nxt = client.get(f"/itineraries/saved/{sid}/next", params={"datetime": "2026-11-01T08:30", "represents": "arrival"})
    assert nxt.status_code == 200 and len(nxt.json()["itineraries"]) == 3
    params = client.calls[-1].url.params
    assert params["from"] == RIVOLI["id"] and params["to"] == GDL["id"]
    assert params["datetime"] == "20261101T083000" and params["datetime_represents"] == "arrival"

    assert client.delete(f"/itineraries/saved/{sid}").status_code == 204
    assert client.get(f"/itineraries/saved/{sid}").status_code == 404
    assert client.get(f"/itineraries/saved/{sid}/next").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"origin": RIVOLI, "destination": RIVOLI},
        {"origin": {**RIVOLI, "type": "position"}, "destination": GDL},  # « Ma position » non sauvegardable
        {"origin": {**RIVOLI, "id": "x y<z>"}, "destination": GDL},
        {"origin": {**RIVOLI, "name": ""}, "destination": GDL},
        {"origin": RIVOLI},
    ],
)
def test_saved_itineraries_validation(client, body):
    assert client.post("/itineraries/saved", json=body).status_code == 422


# --- Date et heure facultatives ------------------------------------------------------------

FIXED_NOW = datetime(2026, 11, 1, 18, 42, 37, tzinfo=PARIS)


@pytest.fixture
def frozen_now(monkeypatch):
    import idf_trains.main as main

    monkeypatch.setattr(main, "now_paris", lambda: FIXED_NOW)


@pytest.mark.parametrize(
    "params, expected_navitia, expected_requested",
    [
        # Heure seule à venir : aujourd'hui à cette heure
        ({"time": "20:15"}, "20261101T201500", "2026-11-01T20:15:00+01:00"),
        # Heure seule égale à l'heure actuelle (à la minute) : aujourd'hui
        ({"time": "18:42"}, "20261101T184200", "2026-11-01T18:42:00+01:00"),
        # Heure seule déjà passée : demain
        ({"time": "08:15"}, "20261102T081500", "2026-11-02T08:15:00+01:00"),
        ({"time": "18:41"}, "20261102T184100", "2026-11-02T18:41:00+01:00"),
        # Heure passée mais date explicite : la date est respectée
        ({"date": "2026-11-01", "time": "08:15"}, "20261101T081500", "2026-11-01T08:15:00+01:00"),
        # Date seule : ce jour-là à l'heure actuelle (à la minute)
        ({"date": "2026-11-05"}, "20261105T184200", "2026-11-05T18:42:00+01:00"),
        # Les deux
        ({"date": "2026-11-05", "time": "07:30"}, "20261105T073000", "2026-11-05T07:30:00+01:00"),
    ],
)
def test_itineraries_optional_date_and_time(client, frozen_now, params, expected_navitia, expected_requested):
    resp = client.get("/itineraries", params={"from": "a:1", "to": "b:2", "represents": "arrival", **params})
    assert resp.status_code == 200, resp.text
    sent = client.calls[0].url.params
    assert sent["datetime"] == expected_navitia and sent["datetime_represents"] == "arrival"
    body = resp.json()
    assert body["requested_at"] == expected_requested and body["represents"] == "arrival"


def test_itineraries_without_date_nor_time_is_now(client, frozen_now):
    body = client.get("/itineraries", params={"from": "a:1", "to": "b:2", "represents": "arrival"}).json()
    assert "datetime" not in client.calls[0].url.params
    assert body["requested_at"] is None and body["represents"] == "departure"


def test_itineraries_datetime_and_date_are_exclusive(client):
    resp = client.get("/itineraries", params={"from": "a:1", "to": "b:2", "datetime": "2026-11-01T08:00", "time": "09:00"})
    assert resp.status_code == 422


@pytest.mark.parametrize("params", [{"time": "25:00"}, {"date": "2026-13-01"}, {"time": "8h"}])
def test_itineraries_invalid_date_or_time(client, params):
    assert client.get("/itineraries", params={"from": "a:1", "to": "b:2", **params}).status_code == 422


def test_saved_itinerary_accepts_time_only(client, frozen_now):
    sid = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL}).json()["id"]
    resp = client.get(f"/itineraries/saved/{sid}/next", params={"time": "09:00", "represents": "arrival"})
    assert resp.status_code == 200
    assert client.calls[-1].url.params["datetime"] == "20261102T090000"  # 9h passée à 18h42 : demain


def test_time_only_rolls_over_to_next_month(client, monkeypatch):
    import idf_trains.main as main

    monkeypatch.setattr(main, "now_paris", lambda: datetime(2026, 11, 30, 23, 50, tzinfo=PARIS))
    client.get("/itineraries", params={"from": "a:1", "to": "b:2", "time": "07:00"})
    assert client.calls[0].url.params["datetime"] == "20261201T070000"


# --- Horaire enregistré et modification d'un itinéraire sauvegardé -------------------------


def test_update_schedule_of_existing_itinerary_is_not_a_duplicate(client):
    """Cas signalé : changer la date d'un itinéraire sauvegardé ne doit pas répondre « déjà sauvegardé »."""
    sid = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "name": "Boulot"}).json()["id"]
    resp = client.patch(
        f"/itineraries/saved/{sid}",
        json={"origin": RIVOLI, "destination": GDL, "schedule": {"mode": "arrival", "date": "2026-11-05", "time": "09:00"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schedule"] == {"mode": "arrival", "date": "2026-11-05", "time": "09:00"}
    assert body["name"] == "Boulot"  # champ non envoyé : inchangé


def test_create_with_schedule_and_partial_updates(client):
    resp = client.post(
        "/itineraries/saved",
        json={"origin": RIVOLI, "destination": GDL, "schedule": {"mode": "departure", "time": "07:45"}},
    )
    saved = resp.json()
    assert saved["schedule"] == {"mode": "departure", "date": None, "time": "07:45"}
    sid = saved["id"]

    # Renommer seulement : l'horaire est conservé
    body = client.patch(f"/itineraries/saved/{sid}", json={"name": "Matin"}).json()
    assert body["name"] == "Matin" and body["schedule"]["time"] == "07:45"
    # Repasser en « maintenant » efface date/heure
    body = client.patch(f"/itineraries/saved/{sid}", json={"schedule": {"mode": "now", "time": "07:45"}}).json()
    assert body["schedule"] == {"mode": "now", "date": None, "time": None}
    # Changer de destination
    tour = {"id": "poi:osm:node:1", "name": "Tour Eiffel (Paris)", "type": "poi"}
    assert client.patch(f"/itineraries/saved/{sid}", json={"destination": tour}).json()["destination"]["name"] == tour["name"]
    # Effacer le nom
    assert client.patch(f"/itineraries/saved/{sid}", json={"name": None}).json()["name"] is None


def test_same_itinerary_saved_several_times_with_different_schedules(client):
    def save(schedule):
        return client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "schedule": schedule})

    a = save({"mode": "departure", "time": "08:00"})
    b = save({"mode": "departure", "time": "17:30"})
    c = save({"mode": "arrival", "time": "08:00"})
    d = save({"mode": "departure", "date": "2026-11-05", "time": "08:00"})
    assert [r.status_code for r in (a, b, c, d)] == [201, 201, 201, 201]
    assert len(client.get("/itineraries/saved").json()) == 4

    # Même horaire exact : doublon
    assert save({"mode": "departure", "time": "08:00"}).status_code == 409
    # Donner à l'un l'horaire d'un autre : doublon
    resp = client.patch(f"/itineraries/saved/{b.json()['id']}", json={"schedule": {"mode": "departure", "time": "08:00"}})
    assert resp.status_code == 409


def test_update_to_an_existing_pair_conflicts(client):
    a = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL}).json()["id"]
    b = client.post("/itineraries/saved", json={"origin": GDL, "destination": RIVOLI}).json()["id"]
    resp = client.patch(f"/itineraries/saved/{b}", json={"origin": RIVOLI, "destination": GDL})
    assert resp.status_code == 409
    # Même paire mais horaire différent : accepté
    resp = client.patch(
        f"/itineraries/saved/{b}",
        json={"origin": RIVOLI, "destination": GDL, "schedule": {"mode": "arrival", "time": "09:00"}},
    )
    assert resp.status_code == 200, resp.text
    assert client.patch(f"/itineraries/saved/{a}", json={"destination": RIVOLI}).status_code == 422  # départ = arrivée


@pytest.mark.parametrize(
    "schedule",
    [{"mode": "arrival", "time": "9h"}, {"mode": "arrival", "date": "2026-02-30"}, {"mode": "later"}],
)
def test_invalid_schedule(client, schedule):
    assert client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "schedule": schedule}).status_code == 422


def test_next_uses_saved_schedule_by_default(client, frozen_now):
    sid = client.post(
        "/itineraries/saved",
        json={"origin": RIVOLI, "destination": GDL, "schedule": {"mode": "arrival", "time": "09:00"}},
    ).json()["id"]

    body = client.get(f"/itineraries/saved/{sid}/next").json()
    sent = client.calls[-1].url.params
    # 9h00 est passée à 18h42 : demain, en heure d'arrivée
    assert sent["datetime"] == "20261102T090000" and sent["datetime_represents"] == "arrival"
    assert body["requested_at"] == "2026-11-02T09:00:00+01:00"

    # Un horaire précisé dans la requête l'emporte
    client.get(f"/itineraries/saved/{sid}/next", params={"time": "20:00"})
    sent = client.calls[-1].url.params
    assert sent["datetime"] == "20261101T200000" and sent["datetime_represents"] == "departure"


def test_old_database_is_migrated(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE saved_itineraries (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, origin_id TEXT NOT NULL, "
        "destination_id TEXT NOT NULL, origin TEXT NOT NULL, destination TEXT NOT NULL, created_at TEXT NOT NULL, "
        "UNIQUE (origin_id, destination_id))"
    )
    con.execute(
        "INSERT INTO saved_itineraries (name, origin_id, destination_id, origin, destination, created_at) "
        "VALUES ('Ancien', 'a:1', 'b:2', '{\"id\": \"a:1\", \"name\": \"A\", \"type\": \"poi\"}', "
        "'{\"id\": \"b:2\", \"name\": \"B\", \"type\": \"poi\"}', '2026-10-01T00:00:00+00:00')"
    )
    con.commit()
    con.close()

    store = ItineraryStore(db)
    [row] = store.list()
    assert row.name == "Ancien" and row.schedule == {"mode": "now", "date": None, "time": None}
    updated = store.update(row.id, schedule={"mode": "arrival", "date": None, "time": "08:30"})
    assert updated.schedule["time"] == "08:30"


def test_migration_drops_old_unique_pair_constraint(tmp_path):
    """Bases créées avant les horaires multiples : la contrainte UNIQUE (départ, arrivée) est retirée."""
    import json
    import sqlite3

    db_path = tmp_path / "old.db"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE saved_itineraries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, origin_id TEXT NOT NULL,
            destination_id TEXT NOT NULL, origin TEXT NOT NULL, destination TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE (origin_id, destination_id)
        );
        """
    )
    db.execute(
        "INSERT INTO saved_itineraries (name, origin_id, destination_id, origin, destination, created_at) "
        "VALUES ('Boulot', ?, ?, ?, ?, '2026-01-01T00:00:00+00:00')",
        (RIVOLI["id"], GDL["id"], json.dumps(RIVOLI), json.dumps(GDL)),
    )
    db.commit()
    db.close()

    store = ItineraryStore(db_path)
    [old] = store.list()
    assert old.name == "Boulot" and old.schedule == {"mode": "now", "date": None, "time": None}
    other = store.create(RIVOLI, GDL, "Soir", {"mode": "departure", "date": None, "time": "18:00"})
    assert other.id != old.id and len(ItineraryStore(db_path).list()) == 2
