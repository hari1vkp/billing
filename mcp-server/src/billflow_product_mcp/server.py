"""FastMCP entrypoint: exactly four product-discovery tools.

Run with stdio (default, process-level trust)::

    python -m billflow_product_mcp.server

Optionally run over HTTP with optional Bearer/X-API-Key auth::

    PRODUCT_MCP_TRANSPORT=streamable-http PRODUCT_MCP_API_KEY=secret \
        python -m billflow_product_mcp.server

This server is a read-only discovery integration. It does not manage stock,
invoices, sales, adjustments, prices or any BillFlow business operation.
"""

from __future__ import annotations

import os
import secrets

from mcp.server.fastmcp import FastMCP

from . import config, services
from .models import (
    BarcodeLookupResult,
    CategoriesResponse,
    ProductDetail,
    SearchResponse,
)

mcp = FastMCP(
    "billflow-product-discovery",
    instructions=(
        "Discover product facts (name, brand, category, pack size and verified external "
        "barcodes) from public Open Food Facts family catalogues. Read-only: no inventory, "
        "pricing or sales operations. Never invent a barcode or a price."
    ),
)


@mcp.tool()
async def search_products(
    query: str,
    category: str | None = None,
    brand: str | None = None,
    page_size: int = 20,
) -> SearchResponse:
    """Search external product catalogues by name, brand, category, pack size or barcode.

    Results include only verified external barcodes, their source and source URL,
    a confidence score, and a ready-to-copy 14-column BillFlow import row.
    Unknown prices are left blank. Sources are selected by category/query and all
    relevant catalogues are queried; failures degrade gracefully with warnings.
    """
    return await services.search_products(
        query=query, category=category, brand=brand, page_size=page_size
    )


@mcp.tool()
async def get_product_details(
    barcode: str | None = None,
    product_id: str | None = None,
    source: str | None = None,
) -> ProductDetail:
    """Return full detail for a barcode (or 'source:code' product_id).

    If neither identifier is supplied, an explicit error result is returned; no
    product facts are fabricated. Includes raw evidence fields from the external
    catalogue and the 14-column BillFlow row.
    """
    return await services.get_product_details(
        barcode=barcode, product_id=product_id, source=source
    )


@mcp.tool()
async def lookup_barcode(
    product_name: str,
    brand: str | None = None,
    size_pack: str | None = None,
    variant: str | None = None,
) -> BarcodeLookupResult:
    """Resolve a manufacturer barcode with strict name/brand/size agreement.

    Status is 'verified', 'not_found' or 'uncertain'. A barcode is returned ONLY
    when a strong name match plus brand agreement (when supplied) AND pack-size
    agreement (when supplied) are all confirmed by an external catalogue record.
    Two package sizes are never assumed to share a barcode.
    """
    return await services.lookup_barcode(
        product_name=product_name,
        brand=brand,
        size_pack=size_pack,
        variant=variant,
    )


@mcp.tool()
def get_product_categories() -> CategoriesResponse:
    """Return the discovery taxonomy with per-category source coverage and caveats."""
    return services.get_categories()


def build_http_app():
    """Build the ASGI app for HTTP transports, optionally enforcing an API key."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    app = mcp.streamable_http_app()
    api_key = config.settings.api_key

    if api_key:
        expected = api_key

        class ApiKeyMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                authorization = request.headers.get("authorization", "")
                provided = ""
                if authorization.lower().startswith("bearer "):
                    provided = authorization[7:].strip()
                if not provided:
                    provided = request.headers.get("x-api-key", "").strip()
                # constant-time comparison; the key itself is never logged.
                if not provided or not secrets.compare_digest(provided, expected):
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(ApiKeyMiddleware)
    return app


def main() -> None:
    transport = config.settings.transport
    if transport in {"streamable-http", "http", "sse"}:
        import uvicorn

        app = build_http_app()
        uvicorn.run(app, host=config.settings.http_host, port=config.settings.http_port)
    else:
        # stdio: trust is process-level. The API key is intentionally not used here.
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
