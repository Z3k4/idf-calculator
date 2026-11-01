import asyncio

import httpx
import pytest

from idf_trains import cache as cache_mod
from idf_trains import prim as prim_mod
from idf_trains.cache import MemoryCache
from idf_trains.prim import PrimClient, PrimError

SIRI = {"Siri": {"ServiceDelivery": {"StopMonitoringDelivery": []}}}


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(cache_mod.time, "monotonic", c)
    monkeypatch.setattr(prim_mod.time, "time", c)
    return c


def run(coro):
    return asyncio.run(coro)


# --- MemoryCache ---------------------------------------------------------------------------


def test_memory_cache_expiry(clock):
    async def scenario():
        c = MemoryCache()
        await c.set("k", {"v": 1}, ttl=10)
        assert await c.get("k") == {"v": 1}
        clock.now += 11
        assert await c.get("k") is None

    run(scenario())


def test_memory_cache_lru_eviction(clock):
    async def scenario():
        c = MemoryCache(max_entries=2)
        await c.set("a", 1, 60)
        await c.set("b", 2, 60)
        await c.get("a")  # « a » devient le plus récent
        await c.set("c", 3, 60)
        assert await c.get("b") is None
        assert await c.get("a") == 1 and await c.get("c") == 3

    run(scenario())


# --- PrimClient + cache --------------------------------------------------------------------


def make_client(handler, **kwargs):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PrimClient(http, "key", "https://prim.test", **kwargs)


def test_hit_miss_and_refresh(clock):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=SIRI)

    async def scenario():
        prim = make_client(handler, cache_ttl=30)
        assert (await prim.stop_monitoring("1")).cache == "MISS"
        clock.now += 10
        res = await prim.stop_monitoring("1")
        assert res.cache == "HIT" and len(calls) == 1
        clock.now += 25  # au-delà de cache_ttl
        assert (await prim.stop_monitoring("1")).cache == "MISS"
        assert len(calls) == 2
        # clés distinctes par gare
        assert (await prim.stop_monitoring("2")).cache == "MISS"

    run(scenario())


def test_stale_if_error(clock):
    state = {"fail": False}

    def handler(request):
        if state["fail"]:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=SIRI)

    async def scenario():
        prim = make_client(handler, cache_ttl=30, stale_ttl=300)
        await prim.stop_monitoring("1")
        state["fail"] = True

        clock.now += 60  # périmé mais encore conservé
        res = await prim.stop_monitoring("1")
        assert res.cache == "STALE" and res.data == SIRI

        clock.now += 300  # au-delà de stale_ttl : plus de secours
        with pytest.raises(PrimError):
            await prim.stop_monitoring("1")

    run(scenario())


def test_concurrent_requests_single_upstream_call():
    calls = []

    async def scenario():
        async def handler(request):
            calls.append(request)
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=SIRI)

        prim = make_client(handler)
        results = await asyncio.gather(*(prim.stop_monitoring("1") for _ in range(10)))
        assert len(calls) == 1
        assert sorted(r.cache for r in results) == ["HIT"] * 9 + ["MISS"]

    run(scenario())
