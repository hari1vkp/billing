"""Simple per-host minimum-interval limiter (politeness, not a hard quota)."""

from __future__ import annotations

import asyncio
import time

from . import config


class HostRateLimiter:
    def __init__(self, min_interval: float | None = None) -> None:
        self.min_interval = (
            config.settings.min_request_interval
            if min_interval is None
            else min_interval
        )
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, host: str) -> asyncio.Lock:
        lock = self._locks.get(host)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[host] = lock
        return lock

    async def wait(self, host: str) -> None:
        """Block until at least ``min_interval`` seconds passed since last request to host."""
        if self.min_interval <= 0:
            return
        async with self._lock_for(host):
            now = time.monotonic()
            last = self._last.get(host)
            if last is not None:
                remaining = self.min_interval - (now - last)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last[host] = time.monotonic()


limiter = HostRateLimiter()
