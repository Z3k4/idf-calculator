"""Suivi de la consommation des API IDFM (appels sortants et requêtes évitées par le cache)."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from .storage import UsageStore

logger = logging.getLogger(__name__)

PARIS = ZoneInfo("Europe/Paris")

# Libellés affichés pour chaque API IDFM
APIS = {
    "realtime": "Temps réel (prochains passages)",
    "navitia": "Calculateur d'itinéraires",
}


def now_paris() -> datetime:
    return datetime.now(PARIS)


class UsageTracker:
    """Enregistre les appels sans jamais faire échouer la requête en cas de problème."""

    def __init__(self, store: UsageStore):
        self.store = store

    async def record_call(self, api: str, endpoint: str, status: int, duration_ms: int) -> None:
        try:
            await asyncio.to_thread(self.store.record_call, api, endpoint, status, duration_ms, now_paris())
        except Exception as exc:  # pragma: no cover
            logger.warning("Suivi de consommation indisponible : %s", exc)

    async def record_cache_hit(self, api: str) -> None:
        try:
            await asyncio.to_thread(self.store.record_cache_hit, api, now_paris())
        except Exception as exc:  # pragma: no cover
            logger.warning("Suivi de consommation indisponible : %s", exc)

    @asynccontextmanager
    async def track(self, api: str, endpoint: str):
        """Mesure un appel HTTP : `with tracker.track(...) as call: call.status = resp.status_code`."""
        call = _Call()
        start = time.perf_counter()
        try:
            yield call
        finally:
            await self.record_call(api, endpoint, call.status, int((time.perf_counter() - start) * 1000))


class _Call:
    status: int = 0  # reste à 0 si l'appel lève une exception (erreur réseau)


@asynccontextmanager
async def nullcall():
    """Équivalent de `track()` quand le suivi est désactivé."""
    yield _Call()
