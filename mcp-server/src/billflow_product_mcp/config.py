"""Environment-driven configuration for the product discovery MCP server.

Secrets are read from the environment only and are never logged. The API key,
when present, is used solely by the optional HTTP/ASGI auth middleware; stdio
transport relies on process-level trust and does not read it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # Descriptive User-Agent: Open Food Facts returns 503 for unidentified clients.
    user_agent: str = os.getenv(
        "PRODUCT_MCP_USER_AGENT",
        "BillFlowProductDiscoveryMCP/0.1 "
        "(https://example.invalid/billflow-product-mcp; product discovery integration; "
        "contact: ops@billflow.local)",
    )
    request_timeout: float = _float_env("PRODUCT_MCP_TIMEOUT", 8.0)
    cache_ttl_seconds: int = _int_env("PRODUCT_MCP_CACHE_TTL", 3600)
    min_request_interval: float = _float_env("PRODUCT_MCP_RATE_LIMIT_INTERVAL", 0.5)
    max_retries: int = _int_env("PRODUCT_MCP_MAX_RETRIES", 2)
    # Optional HTTP auth. Standard base64-free Bearer/X-API-Key comparison at the edge.
    api_key: str | None = os.getenv("PRODUCT_MCP_API_KEY") or None
    http_host: str = os.getenv("PRODUCT_MCP_HOST", "127.0.0.1")
    http_port: int = _int_env("PRODUCT_MCP_PORT", 8001)
    transport: str = os.getenv("PRODUCT_MCP_TRANSPORT", "stdio").strip().lower()


settings = Settings()

# Only these fields are requested from the catalogues; keeps responses small and
# makes it explicit which evidence can legitimately appear in a result.
SEARCH_FIELDS = (
    "code,product_name,product_name_en,brands,brands_tags,categories,"
    "categories_tags,quantity,image_url,image_front_url,generic_name"
)

# Barcodes that look like this are treated as manufacturer/EAN codes (never internal).
BARCODE_MIN_DIGITS = 8
BARCODE_MAX_DIGITS = 14
