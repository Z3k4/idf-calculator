import pytest
from fastapi.testclient import TestClient

from idf_trains.config import settings
from idf_trains.main import app, get_home_store, get_itinerary_store, get_repo, get_store
from idf_trains.stations import StationRepository
from idf_trains.storage import HomeStore, ItineraryStore, JourneyStore

RIVOLI = {"id": "2.3522;48.8566", "name": "12 Rue de Rivoli (Paris)", "type": "address", "city": "Paris"}
GDL = {"id": "stop_area:IDFM:71517", "name": "Gare de Lyon (Paris)", "type": "stop_area", "city": "Paris"}


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "home.db"
    repo = StationRepository.from_file(settings.stations_file)
    stores = {
        get_store: JourneyStore(db),
        get_itinerary_store: ItineraryStore(db),
        get_home_store: HomeStore(db),
        get_repo: repo,
    }
    app.dependency_overrides.update({dep: (lambda v=v: v) for dep, v in stores.items()})
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_home_selection_and_order(client):
    assert client.get("/home").json() == {"items": []}

    j = client.post("/journeys", json={"origin_id": "45102", "destination_id": "470195", "name": "Boulot"}).json()
    it = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "name": "Maison"}).json()

    body = {"items": [{"kind": "itinerary", "id": it["id"]}, {"kind": "journey", "id": j["id"]}]}
    resp = client.put("/home", json=body)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [(i["kind"], i["id"]) for i in items] == [("itinerary", it["id"]), ("journey", j["id"])]
    assert items[0]["itinerary"]["name"] == "Maison" and items[0]["journey"] is None
    assert items[1]["journey"]["origin"]["name"] == "Châtelet - Les Halles"

    # L'ordre est conservé
    assert [i["kind"] for i in client.get("/home").json()["items"]] == ["itinerary", "journey"]

    # Nouvel ordre + doublon ignoré
    body = {"items": [{"kind": "journey", "id": j["id"]}, {"kind": "journey", "id": j["id"]}, {"kind": "itinerary", "id": it["id"]}]}
    assert [i["kind"] for i in client.put("/home", json=body).json()["items"]] == ["journey", "itinerary"]


def test_home_rejects_unknown_items(client):
    assert client.put("/home", json={"items": [{"kind": "journey", "id": 999}]}).status_code == 422
    assert client.put("/home", json={"items": [{"kind": "other", "id": 1}]}).status_code == 422


def test_deleting_a_saved_item_removes_it_from_home(client):
    j = client.post("/journeys", json={"origin_id": "45102", "destination_id": "470195"}).json()
    it = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL}).json()
    client.put("/home", json={"items": [{"kind": "journey", "id": j["id"]}, {"kind": "itinerary", "id": it["id"]}]})

    client.delete(f"/journeys/{j['id']}")
    assert [i["kind"] for i in client.get("/home").json()["items"]] == ["itinerary"]
    client.delete(f"/itineraries/saved/{it['id']}")
    assert client.get("/home").json()["items"] == []
