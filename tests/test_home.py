import sqlite3

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


@pytest.fixture
def saved(client):
    j = client.post("/journeys", json={"origin_id": "45102", "destination_id": "470195", "name": "Boulot"}).json()
    it = client.post("/itineraries/saved", json={"origin": RIVOLI, "destination": GDL, "name": "Maison"}).json()
    return j, it


def default_group(client):
    [group] = client.get("/home").json()["groups"]
    return group


def test_default_group_exists(client):
    assert client.get("/home").json() == {"groups": [{"id": 1, "name": "Accueil", "items": []}]}


def test_group_selection_and_order(client, saved):
    j, it = saved
    gid = default_group(client)["id"]

    body = {"items": [{"kind": "itinerary", "id": it["id"]}, {"kind": "journey", "id": j["id"]}]}
    resp = client.patch(f"/home/groups/{gid}", json=body)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [(i["kind"], i["id"]) for i in items] == [("itinerary", it["id"]), ("journey", j["id"])]
    assert items[0]["itinerary"]["name"] == "Maison" and items[0]["journey"] is None
    assert items[1]["journey"]["origin"]["name"] == "Châtelet - Les Halles"

    # L'ordre est conservé
    assert [i["kind"] for i in default_group(client)["items"]] == ["itinerary", "journey"]

    # Nouvel ordre + doublon ignoré ; le nom n'est pas modifié
    body = {"items": [{"kind": "journey", "id": j["id"]}, {"kind": "journey", "id": j["id"]}, {"kind": "itinerary", "id": it["id"]}]}
    group = client.patch(f"/home/groups/{gid}", json=body).json()
    assert [i["kind"] for i in group["items"]] == ["journey", "itinerary"] and group["name"] == "Accueil"


def test_create_rename_and_delete_groups(client, saved):
    j, it = saved
    resp = client.post("/home/groups", json={"name": " Week-end ", "items": [{"kind": "itinerary", "id": it["id"]}]})
    assert resp.status_code == 201, resp.text
    weekend = resp.json()
    assert weekend["name"] == "Week-end" and [i["id"] for i in weekend["items"]] == [it["id"]]

    groups = client.get("/home").json()["groups"]
    assert [g["name"] for g in groups] == ["Accueil", "Week-end"]
    assert groups[0]["items"] == []  # groupes indépendants

    # Renommer sans toucher aux éléments
    renamed = client.patch(f"/home/groups/{weekend['id']}", json={"name": "Loisirs"}).json()
    assert renamed["name"] == "Loisirs" and len(renamed["items"]) == 1

    assert client.patch(f"/home/groups/{weekend['id']}", json={"name": "   "}).status_code == 422
    assert client.patch("/home/groups/999", json={"name": "X"}).status_code == 404

    assert client.delete(f"/home/groups/{weekend['id']}").status_code == 204
    assert [g["name"] for g in client.get("/home").json()["groups"]] == ["Accueil"]
    # Le dernier groupe ne peut pas être supprimé
    assert client.delete(f"/home/groups/{groups[0]['id']}").status_code == 409


def test_home_rejects_unknown_items(client):
    gid = default_group(client)["id"]
    assert client.patch(f"/home/groups/{gid}", json={"items": [{"kind": "journey", "id": 999}]}).status_code == 422
    assert client.patch(f"/home/groups/{gid}", json={"items": [{"kind": "other", "id": 1}]}).status_code == 422
    assert client.post("/home/groups", json={"name": "X", "items": [{"kind": "journey", "id": 999}]}).status_code == 422
    assert client.post("/home/groups", json={"name": ""}).status_code == 422


def test_deleting_a_saved_item_removes_it_from_all_groups(client, saved):
    j, it = saved
    both = [{"kind": "journey", "id": j["id"]}, {"kind": "itinerary", "id": it["id"]}]
    client.patch(f"/home/groups/{default_group(client)['id']}", json={"items": both})
    client.post("/home/groups", json={"name": "Autre", "items": both})

    client.delete(f"/journeys/{j['id']}")
    assert [[i["kind"] for i in g["items"]] for g in client.get("/home").json()["groups"]] == [["itinerary"], ["itinerary"]]
    client.delete(f"/itineraries/saved/{it['id']}")
    assert all(g["items"] == [] for g in client.get("/home").json()["groups"])


def test_migration_moves_old_selection_into_default_group(tmp_path):
    db_path = tmp_path / "old.db"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE home_items (
            kind TEXT NOT NULL CHECK (kind IN ('journey', 'itinerary')),
            ref_id INTEGER NOT NULL, position INTEGER NOT NULL, PRIMARY KEY (kind, ref_id)
        );
        INSERT INTO home_items VALUES ('itinerary', 3, 0), ('journey', 1, 1);
        """
    )
    db.commit()
    db.close()

    [group] = HomeStore(db_path).list_groups()
    assert group.name == "Accueil" and group.items == [("itinerary", 3), ("journey", 1)]
    # Réouverture : pas de nouvelle migration ni de groupe en double
    assert len(HomeStore(db_path).list_groups()) == 1
