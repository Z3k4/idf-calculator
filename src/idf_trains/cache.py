"""Backends de cache clé/valeur avec expiration : mémoire (défaut) ou Redis (optionnel)."""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: float) -> None: ...
    async def close(self) -> None: ...


class MemoryCache:
    """Cache LRU en mémoire, propre au processus."""

    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    async def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires <= time.monotonic():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl: float) -> None:
        self._data[key] = (time.monotonic() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    async def close(self) -> None:
        self._data.clear()


class RedisCache:
    """Cache partagé entre instances (valeurs sérialisées en JSON)."""

    def __init__(self, url: str, prefix: str = "idf-trains:"):
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Backend Redis : installez l'extra « uv sync --extra redis »") from exc
        self.prefix = prefix
        self._redis = redis.from_url(url)

    # Une panne Redis ne doit pas casser l'API : on se comporte comme un cache vide.
    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._redis.get(self.prefix + key)
        except Exception as exc:
            logger.warning("Cache Redis indisponible (get %s) : %s", key, exc)
            return None
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, ttl: float) -> None:
        try:
            await self._redis.set(self.prefix + key, json.dumps(value), px=int(ttl * 1000))
        except Exception as exc:
            logger.warning("Cache Redis indisponible (set %s) : %s", key, exc)

    async def close(self) -> None:
        await self._redis.aclose()


def create_cache(redis_url: str = "", max_entries: int = 1000) -> Cache:
    return RedisCache(redis_url) if redis_url else MemoryCache(max_entries)
