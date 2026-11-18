"""Pydantic models for every structured tool response.

Nothing in this module performs I/O. All external data is validated into these
shapes by the source adapters (``sources/base.py``) and orchestrated by
``services.py``. Unknown prices are always blank - this server never invents
business data.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# The EXACT 14-column BillFlow import header, in order. Mirrors
# backend/app/services/ai_catalogue_service.py and IMPORT_CONTRACT.md.
BILLFLOW_COLUMNS: tuple[str, ...] = (
    "Product Name",
    "Brand",
    "Category",
    "Subcategory",
    "Variant",
    "Size / Pack Size",
    "Barcode",
    "Barcode Type",
    "SKU",
    "Purchase Price",
    "Selling Price",
    "Discount Type",
    "Discount Value",
    "Opening Stock",
)

BILLFLOW_HEADER: str = ",".join(BILLFLOW_COLUMNS)

BILLFLOW_NOTE: str = (
    "BillFlow row uses the exact 14-column import header. Purchase/Selling Price, "
    "Discount and Opening Stock are left blank (unknown to this discovery service). "
    "Barcode Type is 'manufacturer' ONLY for a barcode verified against an external "
    "catalogue; otherwise it is 'internal' with Barcode blank - BillFlow's backend "
    "generates the internal SKU / Code 128 barcode at import time."
)


def make_billflow_row(
    *,
    product_name: str = "",
    brand: str = "",
    category: str = "",
    subcategory: str = "",
    variant: str = "",
    size_pack: str = "",
    barcode: str = "",
    barcode_type: Literal["manufacturer", "internal"] = "internal",
    sku: str = "",
) -> dict[str, str | None]:
    """Return a dict with exactly the 14 BillFlow header keys, in order.

    Prices / discount / stock are intentionally blank: this server is a product
    *discovery* integration and has no reliable source for them.
    """
    # Only an external, verified barcode may be labelled "manufacturer".
    if barcode_type == "manufacturer" and not barcode.strip():
        barcode_type = "internal"
    row: dict[str, str | None] = {
        "Product Name": product_name or "",
        "Brand": brand or "",
        "Category": category or "",
        "Subcategory": subcategory or "",
        "Variant": variant or "",
        "Size / Pack Size": size_pack or "",
        "Barcode": barcode if barcode_type == "manufacturer" else "",
        "Barcode Type": barcode_type,
        "SKU": sku or "",
        "Purchase Price": "",
        "Selling Price": "",
        "Discount Type": "",
        "Discount Value": "",
        "Opening Stock": "",
    }
    return row


class ProductRecord(BaseModel):
    """One discovered product as returned by ``search_products``."""

    product_name: str
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    size_pack: str = ""
    variant: str = ""
    barcode: str = ""  # populated only when it came from a verified catalogue record
    barcode_status: str = ""  # verified | absent | unknown
    source: str
    source_url: str = ""
    confidence: float = 0.0
    billflow_row: dict[str, str | None] = Field(default_factory=dict)
    notes: str = ""


class SearchResponse(BaseModel):
    products: list[ProductRecord] = Field(default_factory=list)
    sources_queried: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    count: int = 0
    query: str = ""
    category: str | None = None
    brand: str | None = None
    notes: str = BILLFLOW_NOTE


class ProductDetail(BaseModel):
    """Full detail from ``get_product_details`` (also used for explicit errors)."""

    product_name: str = ""
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    size_pack: str = ""
    variant: str = ""
    manufacturer_barcode: str = ""
    barcode_status: str = "not_found"
    source: str = "none"
    source_url: str = ""
    raw_evidence: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    billflow_row: dict[str, str | None] = Field(default_factory=make_billflow_row)
    error: str | None = None
    found: bool = False


class BarcodeLookupResult(BaseModel):
    """Conservative barcode resolution from ``lookup_barcode``."""

    product_name: str = ""
    barcode: str = ""  # ONLY set when status == "verified"
    status: Literal["verified", "not_found", "uncertain"] = "not_found"
    match_score: float = 0.0
    reason: str = ""
    source: str = "none"
    source_url: str = ""
    brand: str = ""
    size_pack: str = ""
    variant: str = ""
    candidates_considered: int = 0
    warnings: list[str] = Field(default_factory=list)
    billflow_row: dict[str, str | None] = Field(default_factory=make_billflow_row)
    notes: str = BILLFLOW_NOTE


class CategoryInfo(BaseModel):
    id: str
    label: str
    description: str = ""
    subcategories: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    coverage_caveat: str = ""
    billflow_category: str = ""


class CategoriesResponse(BaseModel):
    categories: list[CategoryInfo] = Field(default_factory=list)
    billflow_header: str = BILLFLOW_HEADER
    notes: str = (
        "Categories mirror BillFlow's catalogue categories. 'sources' lists the "
        "catalogues with plausible coverage; an empty list means no reliable public "
        "source exists. Coverage caveats are explicit and barcodes are never inferred."
    )
    warnings: list[str] = Field(default_factory=list)
