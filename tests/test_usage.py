import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from idf_trains.config import settings
from idf_trains.main import app, get_usage_store
from idf_trains.navitia import NavitiaClient
from idf_trains.prim import PrimClient, PrimError
from idf_trains.storage import UsageStore
from idf_trains.usage import PARIS, UsageTracker, now_paris

from navitia_fixtures import PLACES

SIRI = {"Siri": {"ServiceDelivery": {"StopMonitoringDelivery": []}}}


@pytest.fixture
def store(tmp_path):
    return UsageStore(tmp_path / "usage.db")


def test_prim_calls_and_cache_hits_are_recorded(store):
    statuses = iter([200, 500])

    def handler(request):
        return httpx.Response(next(statuses), json=SIRI)

    async def scenario():
        prim = PrimClient(
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            "key",
            "https://prim.test",
            cache_ttl=30,
            usage=UsageTracker(store),
        )
        await prim.stop_monitoring("1")  # appel 200
        await prim.stop_monitoring("1")  # cache
        with pytest.raises(PrimError):
            await prim.stop_monitoring("2")  # appel 500

    asyncio.run(scenario())
    day = now_paris().date().isoformat()
    [row] = store.daily(day)
    assert row == {"day": day, "api": "realtime", "calls": 2, "errors": 1, "cache_hits": 1}
    assert [c["status"] for c in store.recent()] == [500, 200]
    assert store.by_endpoint(day)[0]["endpoint"] == "stop-monitoring"


def test_network_error_is_recorded_with_status_0(store):
    def handler(request):
        raise httpx.ConnectError("boom")

    async def scenario():
        navitia = NavitiaClient(
            httpx.AsyncClient(transport=httpx.MockTransport(handler)), "key", "https://x", usage=UsageTracker(store)
        )
        with pytest.raises(PrimError):
            await navitia.places("rivoli")

    asyncio.run(scenario())
    [call] = store.recent()
    assert (call["api"], call["endpoint"], call["status"]) == ("navitia", "places", 0)


def test_navitia_places_cache_hits(store):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=PLACES)

    async def scenario():
        navitia = NavitiaClient(
            httpx.AsyncClient(transport=httpx.MockTransport(handler)), "key", "https://x", usage=UsageTracker(store)
        )
        for _ in range(3):
            await navitia.places("rivoli")

    asyncio.run(scenario())
    [row] = store.daily(now_paris().date().isoformat())
    assert (row["calls"], row["cache_hits"]) == (1, 2) and len(calls) == 1


def test_missing_key_is_not_counted_as_a_call(store):
    async def scenario():
        prim = PrimClient(httpx.AsyncClient(), "", "https://prim.test", usage=UsageTracker(store))
        with pytest.raises(PrimError):
            await prim.stop_monitoring("1")

    asyncio.run(scenario())
    assert store.recent() == []


def test_usage_endpoint(store, monkeypatch):
    today = now_paris()
    yesterday = today - timedelta(days=1)
    for _ in range(3):
        store.record_call("navitia", "journeys", 200, 120, today)
    store.record_call("navitia", "places", 429, 50, today)
    store.record_call("realtime", "stop-monitoring", 200, 80, today)
    store.record_call("realtime", "stop-monitoring", 200, 80, yesterday)
    store.record_cache_hit("navitia", today)

    monkeypatch.setattr(settings, "quota_navitia", 1000)
    monkeypatch.setattr(settings, "quota_realtime", None)
    app.dependency_overrides[get_usage_store] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get("/usage", params={"days": 7}).json()
    finally:
        app.dependency_overrides.clear()

    apis = {a["api"]: a for a in body["apis"]}
    nav = apis["navitia"]
    assert (nav["calls"], nav["errors"], nav["cache_hits"], nav["quota"], nav["remaining"]) == (4, 1, 1, 1000, 996)
    assert apis["realtime"]["calls"] == 1 and apis["realtime"]["quota"] is None
    assert apis["realtime"]["remaining"] is None

    # 7 jours × 2 API, jours sans appel inclus, du plus ancien au plus récent
    assert len(body["daily"]) == 14 and body["daily"][-1]["day"] == today.date().isoformat()
    assert body["endpoints"][0] == {"api": "navitia", "endpoint": "journeys", "calls": 3, "errors": 0, "avg_ms": 120}
    assert len(body["recent"]) == 6
    assert datetime.fromisoformat(body["recent"][0]["at"]).utcoffset() == today.astimezone(PARIS).utcoffset()
    assert {h["hour"] for h in body["hourly"]} == {today.hour}
