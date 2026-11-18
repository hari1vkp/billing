"""Tiny in-process TTL cache for polite reuse of identical catalogue requests."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from . import config


class TTLCache:
    def __init__(self, ttl_seconds: int | None = None) -> None:
        self.ttl = config.settings.cache_ttl_seconds if ttl_seconds is None else ttl_seconds
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        if self.ttl <= 0:
            return None
        async with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if time.monotonic() >= expires:
                self._data.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        async with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        self._data.clear()


# Shared across source adapters within one server process.
cache = TTLCache()
