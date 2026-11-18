"""REAL MCP client tests: launch the server over stdio with ``mcp.ClientSession``.

Run from the repository root::

    mcp-server/.venv/bin/python -m pytest mcp-server/tests -q

Tool-contract tests always run. Assertions that depend on live public catalogues
are skipped (with a clear reason) when those sources cannot be reached, so the
suite is green offline while still exercising the real MCP protocol.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"

EXPECTED_TOOLS = {
    "search_products",
    "get_product_details",
    "lookup_barcode",
    "get_product_categories",
}
EXPECTED_BILLFLOW_COLUMNS = [
    "Product Name", "Brand", "Category", "Subcategory", "Variant", "Size / Pack Size",
    "Barcode", "Barcode Type", "SKU", "Purchase Price", "Selling Price",
    "Discount Type", "Discount Value", "Opening Stock",
]
PRICE_COLUMNS = (
    "Purchase Price", "Selling Price", "Discount Type", "Discount Value", "Opening Stock"
)


def _server_params() -> StdioServerParameters:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "billflow_product_mcp.server"],
        env=env,
        cwd=str(PROJECT),
    )


@contextlib.asynccontextmanager
async def _mcp_session():
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call(session: ClientSession, name: str, **arguments) -> dict:
    result = await session.call_tool(name, arguments=arguments)
    assert not result.isError, f"{name} returned an MCP error: {result.content}"
    assert result.content, f"{name} returned no content"
    text = getattr(result.content[0], "text", None)
    assert text is not None, f"{name} returned non-text content"
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return payload


def _network_available(payload: dict) -> bool:
    warnings = " ".join(str(w) for w in payload.get("warnings", []))
    return (
        "All sources were unreachable" not in warnings
        and "Graceful degradation: sources did not respond" not in warnings
    )


def _skip_if_offline(payload: dict, what: str) -> None:
    if not _network_available(payload):
        pytest.skip(
            f"Live public catalogues unreachable; skipping {what}. "
            f"warnings={payload.get('warnings', [])}"
        )


# --------------------------------------------------------------------------- #
# Tool-contract tests (always run, no network required)                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_tools_list_is_exactly_four():
    async with _mcp_session() as session:
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}
    assert names == EXPECTED_TOOLS, f"unexpected tool set: {names}"


@pytest.mark.asyncio
async def test_get_product_categories_contract():
    async with _mcp_session() as session:
        payload = await _call(session, "get_product_categories")
    assert set(payload) >= {"categories", "billflow_header", "warnings"}
    assert payload["billflow_header"] == ",".join(EXPECTED_BILLFLOW_COLUMNS)
    categories = payload["categories"]
    assert isinstance(categories, list) and len(categories) == 9
    ids = {c["id"] for c in categories}
    assert ids == {
        "grocery", "general", "clothing", "mobile_accessories", "electronics",
        "footwear", "cosmetics", "pharmacy", "other",
    }
    for category in categories:
        assert category["label"] and category["description"]
        assert isinstance(category["subcategories"], list) and category["subcategories"]
        assert isinstance(category["sources"], list)
        assert category["coverage_caveat"]  # explicit caveats, including empty-source categories
        assert category["billflow_category"]
    clothing = next(c for c in categories if c["id"] == "clothing")
    assert clothing["sources"] == [], "clothing has no reliable public source"
    assert "NO RELIABLE PUBLIC SOURCE" in clothing["coverage_caveat"]


@pytest.mark.asyncio
async def test_details_require_identifier_and_shape_row():
    async with _mcp_session() as session:
        payload = await _call(session, "get_product_details")
    assert payload["found"] is False
    assert payload["barcode_status"] == "not_found"
    assert payload["error"], "missing identifier must produce an explicit error"
    row = payload["billflow_row"]
    assert list(row.keys()) == EXPECTED_BILLFLOW_COLUMNS
    for column in PRICE_COLUMNS:
        assert row[column] in ("", None), f"{column} must be blank, got {row[column]!r}"
    assert row["Barcode"] == ""
    assert row["Barcode Type"] == "internal"


@pytest.mark.asyncio
async def test_lookup_barcode_never_fabricates_for_local_product():
    async with _mcp_session() as session:
        payload = await _call(
            session,
            "lookup_barcode",
            product_name="Handmade Blue Cotton Shirt, custom",
            size_pack="M",
        )
    assert payload["status"] in {"not_found", "uncertain"}
    assert payload["barcode"] == "", "no barcode may be invented for a local product"
    assert payload["reason"]
    assert 0.0 <= payload["match_score"] <= 1.0
    row = payload["billflow_row"]
    assert list(row.keys()) == EXPECTED_BILLFLOW_COLUMNS
    assert row["Barcode"] == ""
    assert row["Barcode Type"] == "internal"


# --------------------------------------------------------------------------- #
# Live-source tests (contract always checked; live assertions skip if offline)  #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_search_products_returns_real_structured_products():
    async with _mcp_session() as session:
        payload = await _call(
            session, "search_products", query="Maggi", category="grocery", page_size=10
        )
    # Contract - always asserted.
    assert set(payload) >= {
        "products", "sources_queried", "warnings", "count", "query", "category",
    }
    assert payload["query"] == "Maggi"
    assert isinstance(payload["sources_queried"], list) and payload["sources_queried"]
    assert "openfoodfacts" in payload["sources_queried"]
    assert isinstance(payload["products"], list)
    assert payload["count"] == len(payload["products"])
    for product in payload["products"]:
        for field in (
            "product_name", "brand", "category", "subcategory", "size_pack", "variant",
            "barcode", "barcode_status", "source", "source_url", "confidence",
            "billflow_row",
        ):
            assert field in product, f"missing field {field}"
        assert list(product["billflow_row"].keys()) == EXPECTED_BILLFLOW_COLUMNS

    print(f"\n[mcp] search sources_queried={payload['sources_queried']}")
    print(f"[mcp] search warnings={payload['warnings']}")
    print(f"[mcp] search count={payload['count']}")

    _skip_if_offline(payload, "live product assertions")
    if not payload["products"]:
        pytest.skip(
            "Live catalogues responded but returned no validated products for 'Maggi'; "
            f"warnings={payload['warnings']}"
        )
    real = [p for p in payload["products"] if p["product_name"] and p["source"]]
    assert real, "expected at least one real named product from a source"
    verified = [p for p in real if p["barcode_status"] == "verified" and p["barcode"]]
    assert verified, "expected at least one source-verified manufacturer barcode"
    assert all(p["source_url"].startswith("https://") for p in verified)
    assert payload["count"] > 0


@pytest.mark.asyncio
async def test_get_product_details_from_searched_barcode():
    async with _mcp_session() as session:
        search = await _call(
            session, "search_products", query="Maggi", category="grocery", page_size=10
        )
        _skip_if_offline(search, "barcode detail lookup")
        candidates = [
            p for p in search["products"]
            if p["barcode_status"] == "verified" and p["barcode"].isdigit()
        ]
        if not candidates:
            pytest.skip("No verified barcode in search results; cannot test detail lookup.")
        barcode = candidates[0]["barcode"]
        detail = await _call(session, "get_product_details", barcode=barcode)

    assert set(detail) >= {
        "product_name", "brand", "category", "subcategory", "size_pack", "variant",
        "manufacturer_barcode", "barcode_status", "source", "source_url",
        "raw_evidence", "notes", "billflow_row", "found",
    }
    assert list(detail["billflow_row"].keys()) == EXPECTED_BILLFLOW_COLUMNS
    print(f"[mcp] detail barcode={barcode} found={detail['found']} source={detail['source']}")
    if not detail["found"]:
        pytest.skip(f"Catalogue did not return detail for barcode {barcode}.")
    assert detail["manufacturer_barcode"] == barcode
    assert detail["barcode_status"] == "verified"
    assert detail["source_url"].startswith("https://")
    assert detail["raw_evidence"], "detail must include raw evidence fields"
    assert detail["billflow_row"]["Barcode Type"] == "manufacturer"
    assert detail["billflow_row"]["Barcode"] == barcode
    for column in PRICE_COLUMNS:
        assert detail["billflow_row"][column] in ("", None)


@pytest.mark.asyncio
async def test_lookup_barcode_verified_for_known_product():
    async with _mcp_session() as session:
        search = await _call(
            session, "search_products", query="Maggi", category="grocery", page_size=10
        )
        _skip_if_offline(search, "verified barcode lookup")
        candidates = [
            p for p in search["products"]
            if p["product_name"] and p["barcode_status"] == "verified" and p["barcode"]
        ]
        if not candidates:
            pytest.skip("No verified product available to test barcode lookup.")
        target = candidates[0]
        result = await _call(
            session,
            "lookup_barcode",
            product_name=target["product_name"],
            brand=target["brand"] or None,
        )

    assert set(result) >= {
        "product_name", "barcode", "status", "match_score", "reason", "source",
        "source_url", "billflow_row",
    }
    assert result["status"] in {"verified", "not_found", "uncertain"}
    print(
        f"[mcp] lookup status={result['status']} score={result['match_score']} "
        f"source={result['source']} reason={result['reason'][:120]}"
    )
    if result["status"] != "verified":
        warnings_text = " ".join(str(w) for w in result.get("warnings", [])).lower()
        if any(token in warnings_text for token in ("unreachable", "unavailable", "http 503", "http 429")):
            pytest.skip(
                "Live catalogues were unreachable during barcode lookup; "
                f"warnings={result.get('warnings', [])}"
            )
    assert result["status"] == "verified", f"expected verified for known product: {result['reason']}"
    assert result["barcode"].isdigit()
    assert result["source_url"].startswith("https://")
    assert result["billflow_row"]["Barcode Type"] == "manufacturer"
    assert result["billflow_row"]["Barcode"] == result["barcode"]


@pytest.mark.asyncio
async def test_general_electronics_query_is_structured_or_warns():
    async with _mcp_session() as session:
        payload = await _call(
            session,
            "search_products",
            query="wireless bluetooth speaker",
            category="electronics",
            page_size=5,
        )
    assert set(payload) >= {"products", "sources_queried", "warnings", "count"}
    assert isinstance(payload["products"], list)
    assert payload["count"] == len(payload["products"])
    # Either we get structured results, or explicit coverage/unavailability warnings.
    assert payload["products"] or payload["warnings"], (
        "electronics query must return products or a clear coverage warning"
    )
    if not payload["products"]:
        assert any(
            "coverage" in w.lower() or "source" in w.lower() or "unreachable" in w.lower()
            or "no validated products" in w.lower()
            for w in payload["warnings"]
        ), f"unhelpful warnings for empty result: {payload['warnings']}"
    print(f"[mcp] electronics sources={payload['sources_queried']} warnings={payload['warnings']}")
