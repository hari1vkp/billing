# BillFlow Product Discovery MCP server

A **separate, read-only integration** that helps an AI assistant discover real
product facts — name, brand, category, pack size, and *verified* manufacturer
barcodes — from public product catalogues. It is **not** an inventory-management
server: it does **not** manage stock, invoices, sales, adjustments, prices,
discounts, SKUs, tenants, users or any other BillFlow business operation.

It exposes **exactly four MCP tools** and returns a ready-to-copy **14-column
BillFlow import row** with unknown pricing/stock fields left blank.

---

## Architecture

```
mcp-server/
  requirements.txt                 mcp 1.x, httpx, pydantic, pytest, pytest-asyncio, uvicorn
  pyproject.toml                   editable install + module path + pytest config
  src/billflow_product_mcp/
    server.py                      FastMCP instance, 4 tools, stdio/HTTP entrypoint
    config.py                      env config, User-Agent, timeouts, cache TTL, rate limits, API key
    models.py                      Pydantic response models + exact 14-column billflow_row builder
    taxonomy.py                    9 BillFlow categories, subcategories, source coverage mapping
    cache.py                       small TTL cache (default 1h)
    rate_limit.py                  per-host minimum-interval limiter (default 0.5s)
    services.py                    search/detail/barcode orchestration, validation, scoring, shaping
    sources/
      base.py                      ProductSource protocol + validated BaseProductSource adapter
      openfoodfacts.py             world.openfoodfacts.org (food / grocery)
      openbeautyfacts.py           world.openbeautyfacts.org (beauty / personal care)
      openproductsfacts.py         world.openproductsfacts.org (general products)
      registry.py                  source selection by category / query
  tests/test_mcp_client.py         real MCP client tests via stdio
```

Data flow:

```
tool call -> services.py -> taxonomy.select_sources() -> source registry
          -> adapters (httpx + TTL cache + per-host rate limit + retry/backoff)
          -> Pydantic validation of external JSON (malformed records ignored)
          -> confidence scoring / strict barcode verification
          -> structured Pydantic response + 14-column billflow_row
```

`mcp>=1.20,<2` is pinned: the `FastMCP` API used here was renamed to `MCPServer`
in mcp 2.x. Any 1.x release from 1.20 up is supported.

---

## Setup

```bash
cd mcp-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# stdio (default; used by desktop AI clients)
PYTHONPATH=src .venv/bin/python -m billflow_product_mcp.server

# or editable install
.venv/bin/pip install -e .
billflow-product-mcp
```

Configure with environment variables (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRODUCT_MCP_USER_AGENT` | descriptive BillFlow UA | Required by Open Food Facts (503 without one) |
| `PRODUCT_MCP_TIMEOUT` | `8.0` | httpx request timeout (seconds) |
| `PRODUCT_MCP_CACHE_TTL` | `3600` | TTL cache lifetime (seconds) |
| `PRODUCT_MCP_RATE_LIMIT_INTERVAL` | `0.5` | minimum interval per host (seconds) |
| `PRODUCT_MCP_MAX_RETRIES` | `2` | retries on 429 / 5xx with exponential backoff |
| `PRODUCT_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `PRODUCT_MCP_HOST` / `PRODUCT_MCP_PORT` | `127.0.0.1` / `8001` | HTTP bind address |
| `PRODUCT_MCP_API_KEY` | unset | optional HTTP auth secret (never logged) |

### stdio client config example

```json
{
  "mcpServers": {
    "billflow-products": {
      "command": "/abs/path/mcp-server/.venv/bin/python",
      "args": ["-m", "billflow_product_mcp.server"],
      "env": {
        "PYTHONPATH": "/abs/path/mcp-server/src"
      }
    }
  }
}
```

stdio relies on **process-level trust** (whoever can launch the process can use
the tools); the API key is intentionally not checked on stdio.

---

## Tools (exact names, no others)

### 1. `search_products`
`query: str, category?: str, brand?: str, page_size: int = 20` → `SearchResponse`

Systematically queries every catalogue with plausible coverage for the
category/query (never just 2–3 results; fills up to `page_size`). If the query
looks like an EAN (8–14 digits), it performs barcode lookups instead. Returns
`products[]` with `product_name, brand, category, subcategory, size_pack,
variant, barcode` (only when source-verified), `barcode_status, source,
source_url, confidence, billflow_row`, plus `sources_queried, warnings, count`.

### 2. `get_product_details`
`barcode?: str, product_id?: str, source?: str` → `ProductDetail`

Full detail including `manufacturer_barcode`, `barcode_status`, `source`,
`source_url`, `raw_evidence` (raw external fields, API URL, queried URLs,
warnings), `notes` and `billflow_row`. `product_id` accepts `source:code`.
If neither `barcode` nor `product_id` is supplied, an explicit `error` result is
returned — nothing is fabricated.

### 3. `lookup_barcode`
`product_name: str, brand?: str, size_pack?: str, variant?: str` → `BarcodeLookupResult`

A barcode is returned **only** for a strict match: strong name similarity
(≥ 0.80) **plus** brand agreement when `brand` is supplied **plus** pack-size
agreement when `size_pack` is supplied, confirmed by an external catalogue
record. `status` is `verified | not_found | uncertain`; two package sizes are
never assumed to share a barcode; conflicting barcodes are rejected. A
non-verified result always has an **empty** barcode and an internal BillFlow row.

### 4. `get_product_categories`
`()` → `CategoriesResponse`

The 9-category taxonomy (grocery, general, clothing, mobile accessories,
electronics, footwear, cosmetics, pharmacy, other) with subcategories, plausible
sources and explicit coverage caveats.

---

## Authentication (HTTP transport only)

Set `PRODUCT_MCP_API_KEY` and run with `PRODUCT_MCP_TRANSPORT=streamable-http`.
A Starlette/ASGI middleware rejects requests without a matching
`Authorization: Bearer <key>` or `X-API-Key` header (HTTP 401). The comparison is
constant-time and the secret is never logged. Without the env var the HTTP
server is left unauthenticated — bind it to localhost / put it behind your own
gateway. stdio is process-level trust by design.

---

## Sources and coverage

All adapters share one interface (`ProductSource`) and use a descriptive
User-Agent, timeouts, per-host rate limiting, a 1h TTL cache and retry/backoff on
429/5xx. Every result carries its source name and a source URL.

| Source | Host | Coverage |
| --- | --- | --- |
| `openfoodfacts` | `world.openfoodfacts.org` | Branded packaged food/grocery; some household consumables |
| `openbeautyfacts` | `world.openbeautyfacts.org` | Cosmetics, beauty and personal care |
| `openproductsfacts` | `world.openproductsfacts.org` | General/non-food consumer goods |

**Honest API notes / limitations**

- The official docs state that full-text search is **not** supported by
  `/api/v2/search` (it is tag/structured-search only). Full-text search therefore
  uses the catalogue hosts' legacy `/cgi/search.pl?search_terms=...` endpoint;
  barcode detail reads use `/api/v2/product/<code>`. Open Food Facts search also
  falls back to the newer Search-a-licious service (`search.openfoodfacts.org`)
  when the legacy endpoint returns nothing. These are still the official Open
  Food Facts family services.
- **No source provides reliable prices, discounts, GST or stock.** Those
  BillFlow columns are always blank; never treat a discovered row as a priced
  product master.
- **No reliable public source exists for clothing** (and coverage is weak for
  mobile accessories, electronics, footwear and pharmacy). Those categories
  return explicit coverage caveats. Barcodes are per-SKU; they are never inferred
  or shared between sizes/colours.
- Coverage of Indian regional brands, loose/unpackaged goods and new launches is
  patchy. Treat results as discovery leads that a human must review.
- Graceful degradation: if every source fails, tools return a structured result
  with `warnings` and `sources_queried` (or `found: false` / `status:
  not_found`), never an unhandled exception.

---

## BillFlow workflow

1. Discover: call `search_products("Maggi", category="grocery")`.
2. Confirm: call `get_product_details(barcode=<candidate barcode>)` to inspect the
   raw evidence before trusting it.
3. Optional check: `lookup_barcode(product_name=..., brand=..., size_pack=...)`
   to get a conservative barcode decision for a known product.
4. Copy each result's `billflow_row` into BillFlow's **exact 14-column** import
   template:
   `Product Name,Brand,Category,Subcategory,Variant,Size / Pack Size,Barcode,Barcode Type,SKU,Purchase Price,Selling Price,Discount Type,Discount Value,Opening Stock`
5. `Barcode Type` is `manufacturer` **only** for a source-verified external
   barcode. Otherwise it is `internal` with `Barcode` blank — BillFlow's Python
   backend generates the internal SKU / Code 128 barcode during import.
6. Fill in prices, discount and opening stock in BillFlow's editable preview
   (this server deliberately leaves them blank), then parse/commit through the
   existing BillFlow import flow. Nothing here writes to BillFlow directly.

---

## Tests and verification

```bash
mcp-server/.venv/bin/python -m pytest mcp-server/tests -q
mcp-server/.venv/bin/python -m compileall -q mcp-server/src
```

`tests/test_mcp_client.py` launches the real server with
`mcp.client.stdio.stdio_client` + `ClientSession` and `python -m
billflow_product_mcp.server`. Tool-contract tests always run; live-catalogue
assertions are skipped with a clear reason when the public sources cannot be
reached.
