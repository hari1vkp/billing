"""Open Food Facts adapter - food & grocery (world.openfoodfacts.org)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .. import config
from ..taxonomy import SOURCE_FOOD
from .base import BaseProductSource, SourceResponse

# Search-a-licious is OFF's modern full-text search service. The legacy CGI
# endpoint is used first; this is a fallback for when it degrades (the OFF docs
# deprecate /cgi/search.pl and it has had outages).
SEARCH_ALICIOUS = "https://search.openfoodfacts.org/search"


class OpenFoodFactsSource(BaseProductSource):
    name = SOURCE_FOOD
    host = "world.openfoodfacts.org"

    async def search(
        self,
        query: str,
        *,
        brand: str | None = None,
        category: str | None = None,
        page_size: int = 20,
    ) -> SourceResponse:
        result = await super().search(query, brand=brand, category=category, page_size=page_size)
        # The legacy CGI endpoint is deprecated and intermittently returns 503.
        # Use the modern full-text service whenever it yielded nothing, including
        # when the primary request itself failed (result.available == False).
        if not result.products and query:
            await self._search_via_alicious(query, result, page_size)
            if result.products:
                result.available = True
        return result

    async def _search_via_alicious(
        self, query: str, result: SourceResponse, page_size: int
    ) -> None:
        """Secondary full-text backend; failures here are warnings, never exceptions."""
        params: dict[str, Any] = {"q": query, "page_size": max(1, min(int(page_size), 100))}
        url = f"{SEARCH_ALICIOUS}?{urlencode(params)}"
        headers = {
            "User-Agent": config.settings.user_agent,
            "Accept": "application/json",
        }
        import httpx

        await self._limiter.wait("search.openfoodfacts.org")
        try:
            async with httpx.AsyncClient(
                headers=headers, timeout=httpx.Timeout(config.settings.request_timeout)
            ) as client:
                response = await client.get(url)
        except Exception as exc:  # network error -> graceful degradation
            result.warnings.append(
                f"{self.name}: full-text fallback unavailable ({type(exc).__name__})."
            )
            return
        if response.status_code != 200:
            result.warnings.append(
                f"{self.name}: full-text fallback HTTP {response.status_code}."
            )
            return
        try:
            payload = response.json()
        except ValueError:
            result.warnings.append(f"{self.name}: full-text fallback non-JSON response.")
            return
        result.queried_urls.append(url)
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            return
        for raw in hits:
            validated = self._validate_record(raw)
            if validated is not None:
                result.products.append(validated)
