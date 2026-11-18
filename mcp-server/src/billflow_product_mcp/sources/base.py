"""Common, pluggable interface for external product-catalogue sources.

Every adapter returns validated :class:`RawExternalProduct` records. External JSON
is parsed with Pydantic; malformed or incomplete records are ignored rather than
echoed back as facts. All HTTP goes through :meth:`BaseProductSource._request_json`
which applies the shared TTL cache, per-host rate limit and retry/backoff policy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .. import config


class RawExternalProduct(BaseModel):
    """A single external catalogue record, validated and normalized.

    ``code`` is the manufacturer/EAN barcode *as supplied by the source*. It is
    never generated or guessed by this server.
    """

    model_config = ConfigDict(extra="ignore")

    code: str = ""
    product_name: str = ""
    brands: str = ""
    categories: str = ""
    quantity: str = ""
    variant: str = ""
    image_url: str = ""
    categories_tags: list[str] = Field(default_factory=list)
    brands_tags: list[str] = Field(default_factory=list)

    @field_validator("code", "product_name", "quantity", "variant", "image_url", mode="before")
    @classmethod
    def _as_clean_str(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("brands", "categories", mode="before")
    @classmethod
    def _join_list_fields(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v).strip() for v in value if str(v).strip())
        return str(value).strip()

    @field_validator("categories_tags", "brands_tags", mode="before")
    @classmethod
    def _tags_to_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        if isinstance(value, (list, tuple)):
            return [str(v).strip() for v in value if str(v).strip()]
        return []

    @model_validator(mode="after")
    def _require_usable_record(self) -> "RawExternalProduct":
        if not self.code:
            raise ValueError("record has no barcode/code")
        if not (self.product_name or self.brands or self.categories):
            raise ValueError("record has no identifying name, brand or category")
        return self


@dataclass
class SourceResponse:
    """Result of one adapter call, including diagnostics for graceful degradation."""

    source: str
    products: list[RawExternalProduct] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    queried_urls: list[str] = field(default_factory=list)
    raw_evidence: dict[str, Any] = field(default_factory=dict)
    available: bool = True  # False when the source could not be reached at all


@runtime_checkable
class ProductSource(Protocol):
    """Pluggable source interface implemented by every catalogue adapter."""

    name: str
    host: str

    async def search(
        self,
        query: str,
        *,
        brand: str | None = None,
        category: str | None = None,
        page_size: int = 20,
    ) -> SourceResponse: ...

    async def get_by_barcode(self, barcode: str) -> SourceResponse: ...


class BaseProductSource:
    """Shared HTTP/validation implementation for the Open Food Facts family hosts."""

    name: str = "base"
    host: str = ""
    # Full-text search on the OFF family is only available via the legacy CGI
    # endpoint; /api/v2/search is structured/tag-only (verified against the
    # official docs). Barcode reads use /api/v2/product/<code>.
    search_path: str = "/cgi/search.pl"
    product_path: str = "/api/v2/product"

    def __init__(self) -> None:
        from ..cache import cache
        from ..rate_limit import limiter

        self._cache = cache
        self._limiter = limiter

    @property
    def base_url(self) -> str:
        return f"https://{self.host}"

    def product_url(self, code: str) -> str:
        return f"{self.base_url}/product/{code}" if code else self.base_url

    def _validate_record(self, raw: dict[str, Any]) -> RawExternalProduct | None:
        """Validate one external record; return None for malformed input."""
        if not isinstance(raw, dict):
            return None
        payload = {
            "code": raw.get("code") or raw.get("barcode") or "",
            "product_name": (
                raw.get("product_name")
                or raw.get("product_name_en")
                or raw.get("generic_name")
                or ""
            ),
            "brands": raw.get("brands") or raw.get("brands_tags") or "",
            "categories": raw.get("categories") or raw.get("categories_tags") or "",
            "quantity": raw.get("quantity") or "",
            "variant": raw.get("variants") or raw.get("variant") or "",
            "image_url": raw.get("image_front_url") or raw.get("image_url") or "",
            "categories_tags": raw.get("categories_tags") or [],
            "brands_tags": raw.get("brands_tags") or [],
        }
        try:
            return RawExternalProduct.model_validate(payload)
        except Exception:
            # Pydantic ValidationError (and any unexpected coercion issue) means
            # the record is not trustworthy - skip it silently.
            return None

    async def _request_json(
        self,
        path: str,
        params: dict[str, Any] | None,
        warnings: list[str],
        urls: list[str],
    ) -> dict[str, Any] | None:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return await self._fetch_json(url, warnings, urls, host=self.host)

    async def _fetch_json(
        self,
        url: str,
        warnings: list[str],
        urls: list[str],
        *,
        host: str,
    ) -> dict[str, Any] | None:
        urls.append(url)

        cached = await self._cache.get(url)
        if cached is not None:
            return cached

        headers = {
            "User-Agent": config.settings.user_agent,
            "Accept": "application/json",
        }
        timeout = httpx.Timeout(config.settings.request_timeout)
        last_error = "unknown error"

        for attempt in range(config.settings.max_retries + 1):
            await self._limiter.wait(host)
            try:
                async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(url)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < config.settings.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                warnings.append(f"{self.name}: request failed ({last_error}).")
                return None

            if response.status_code == 429 or 500 <= response.status_code < 600:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                except ValueError:
                    delay = 0.5 * (2**attempt)
                if attempt < config.settings.max_retries:
                    await asyncio.sleep(min(delay, 5.0))
                    continue
                warnings.append(
                    f"{self.name}: HTTP {response.status_code} after retries; source unavailable."
                )
                return None

            if response.status_code != 200:
                warnings.append(f"{self.name}: HTTP {response.status_code}; source unavailable.")
                return None

            try:
                payload = response.json()
            except ValueError:
                warnings.append(f"{self.name}: non-JSON response; source unavailable.")
                return None
            if not isinstance(payload, dict):
                warnings.append(f"{self.name}: unexpected JSON shape; source unavailable.")
                return None

            await self._cache.set(url, payload)
            return payload

        warnings.append(f"{self.name}: {last_error}.")
        return None

    async def search(
        self,
        query: str,
        *,
        brand: str | None = None,
        category: str | None = None,
        page_size: int = 20,
    ) -> SourceResponse:
        result = SourceResponse(source=self.name)
        params = {
            "search_terms": query,
            "json": "true",
            "page_size": max(1, min(int(page_size), 100)),
            "fields": config.SEARCH_FIELDS,
        }
        payload = await self._request_json(self.search_path, params, result.warnings, result.queried_urls)
        if payload is None:
            result.available = False
            return result
        raw_products = payload.get("products") or payload.get("hits") or []
        if not isinstance(raw_products, list):
            result.warnings.append(f"{self.name}: malformed product list; ignored.")
            return result
        for raw in raw_products:
            validated = self._validate_record(raw)
            if validated is not None:
                result.products.append(validated)
        return result

    async def get_by_barcode(self, barcode: str) -> SourceResponse:
        result = SourceResponse(source=self.name)
        code = "".join(ch for ch in str(barcode or "") if ch.isdigit())
        if not code:
            result.warnings.append(f"{self.name}: invalid barcode supplied.")
            return result
        path = f"{self.product_path}/{code}"
        payload = await self._request_json(path, {"fields": config.SEARCH_FIELDS}, result.warnings, result.queried_urls)
        if payload is None:
            result.available = False
            return result
        if payload.get("status") != 1 or not isinstance(payload.get("product"), dict):
            # A well-formed "not found" is not a source failure.
            return result
        raw = dict(payload["product"])
        raw.setdefault("code", payload.get("code") or code)
        validated = self._validate_record(raw)
        if validated is None:
            result.warnings.append(f"{self.name}: barcode record failed validation; ignored.")
            payload["_ignored_record"] = True
        result.raw_evidence = {
            "api_url": f"{self.base_url}{path}",
            "status": payload.get("status"),
            "status_verbose": payload.get("status_verbose"),
            "raw": raw,
        }
        if validated is not None:
            result.products.append(validated)
        return result
