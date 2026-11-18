"""Product onboarding helpers: CSV/XLSX parsing, batch commit, barcode lookup and OCR.

Everything here writes through the *existing* Product / StockMovement /
ActivityLog models via ``product_service``, ``inventory_service`` and
``audit_service`` — there is deliberately no parallel product system.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import secrets
import subprocess
from urllib.parse import quote

import httpx
from sqlalchemy import func, select

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import audit_service, inventory_service, product_service
from app.services.ai_catalogue_service import CATALOGUE_HEADER

logger = logging.getLogger(__name__)

OCR_UNAVAILABLE_MESSAGE = (
    "OCR is not available on this server. Use CSV import or manual entry."
)

# Canonical column -> aliases. Matching is case/space/punctuation insensitive
# (see IMPORT_CONTRACT.md).
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["name", "product", "product name", "item", "item name", "description"],
    "brand": ["brand", "brand name", "make", "manufacturer", "company"],
    "category": ["category", "group", "product group", "product category", "department"],
    "subcategory": ["subcategory", "sub category", "sub-category", "sub group", "section"],
    "variant": ["variant", "variation", "colour", "color", "shade", "flavour", "flavor", "model"],
    "size_pack": [
        "size / pack size", "size", "pack size", "pack", "size pack", "unit", "volume"
    ],
    "barcode": ["barcode", "bar code", "ean", "upc", "isbn"],
    "barcode_type": ["barcode type", "bar code type", "code type", "barcode kind"],
    "sku": ["sku", "product code", "item code", "style code", "article no", "article number"],
    "cost_price": ["cost", "cost price", "purchase price", "buying price", "mrp cost"],
    "selling_price": [
        "price", "selling price", "sale price", "retail price", "rate", "mrp"
    ],
    "discount_type": ["discount type", "discount kind"],
    "discount_value": ["discount value", "discount", "discount %", "disc value"],
    "quantity": [
        "quantity", "qty", "stock", "opening stock", "opening qty", "closing stock"
    ],
    # Optional legacy column: defaults from the business settings when absent.
    "gst_rate": ["gst", "gst %", "tax", "tax rate"],
}

# Canonical JSON keys. gst_rate is recognised but is not part of the official
# 14-column template header (it remains optional and is defaulted).
CANONICAL_COLUMNS = [
    "name",
    "brand",
    "category",
    "subcategory",
    "variant",
    "size_pack",
    "barcode",
    "barcode_type",
    "sku",
    "cost_price",
    "selling_price",
    "discount_type",
    "discount_value",
    "quantity",
    "gst_rate",
]

TEMPLATE_HEADER = CATALOGUE_HEADER
TEMPLATE_INSTRUCTIONS = [
    "# Fill one product per row. Leave any cell completely blank when you do not know "
    "its value - never guess a barcode or a price.",
    "# Barcode: type a genuine printed barcode only if you can see it; otherwise leave "
    "it blank and use Barcode Type 'internal'. Discount Type: none | percent | flat.",
]
TEMPLATE_EXAMPLE_ROWS = [
    [
        "Amul Butter",
        "Amul",
        "Dairy",
        "Butter",
        "Unsalted",
        "500 g",
        "8901234567890",
        "manufacturer",
        "AMUL-BTR-500",
        "210",
        "245",
        "none",
        "",
        "10",
    ],
    [
        "Cotton T-Shirt",
        "Roadster",
        "Clothing",
        "T-Shirts",
        "Round Neck / Blue",
        "M",
        "",
        "internal",
        "TSHIRT-BLU-M",
        "250",
        "599",
        "percent",
        "10",
        "5",
    ],
]

DISCOUNT_TYPES = {"none", "percent", "flat"}
_MANUFACTURER_TYPES = {
    "manufacturer", "manufacturers", "gs1", "ean", "upc", "printed", "external"
}
_INTERNAL_TYPES = {"internal", "generated", "billflow", "own"}


class ParseError(Exception):
    """Raised when an uploaded file cannot be read at all."""


class OcrUnavailable(Exception):
    """Raised when no OCR engine is installed on the server."""


def _normalize_header(value) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


_ALIAS_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_LOOKUP[_normalize_header(_alias)] = _canonical


def _normalize_barcode(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    # Spreadsheet apps sometimes coerce long EANs into scientific notation.
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text or None


def _number(raw) -> tuple[float | None, bool, bool]:
    """Parse a cell into (value, ok, provided).

    ``provided`` is False for a blank cell, ``ok`` is False for a non-number.
    """
    if raw is None:
        return None, True, False
    if isinstance(raw, bool):
        return None, False, True
    text = str(raw).strip()
    if not text:
        return None, True, False
    cleaned = text.replace(",", "").replace("\u20b9", "").replace("$", "").strip()
    cleaned = re.sub(r"^\s*(?:rs\.?|inr)\s*", "", cleaned, flags=re.IGNORECASE).strip()
    if not cleaned:
        return None, True, False
    try:
        return float(cleaned), True, True
    except (TypeError, ValueError):
        return None, False, True


def _cell_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_discount_type(raw) -> tuple[str, bool]:
    """Return (canonical value, is_recognised). Blank means 'none'."""
    text = (
        _cell_text(raw)
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("%", " percent")
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "none", True
    synonyms = {
        "no discount": "none",
        "nodiscount": "none",
        "zero": "none",
        "percentage": "percent",
        "pct": "percent",
        "percent off": "percent",
        "flat amount": "flat",
        "rupees": "flat",
        "rs": "flat",
    }
    text = synonyms.get(text, text.replace(" ", ""))
    return text, text in DISCOUNT_TYPES


def _normalize_barcode_type(raw) -> str | None:
    text = _cell_text(raw).lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if text in _MANUFACTURER_TYPES:
        return "manufacturer"
    if text in _INTERNAL_TYPES:
        return "internal"
    return text


def _validate_discount(raw_type, raw_value, errors: list[str]) -> tuple[str, float]:
    discount_type, recognized = _normalize_discount_type(raw_type)
    if not recognized:
        errors.append("Discount type must be one of: none, percent, flat")
        discount_type = "none"

    value, ok, provided = _number(raw_value)
    if provided and not ok:
        errors.append("Discount value must be a number")
    if value is not None:
        if value < 0:
            errors.append("Discount value cannot be negative")
        elif discount_type == "percent" and value > 100:
            errors.append("Discount value cannot exceed 100 for percent discounts")
    if not provided or not ok or value is None:
        value = 0.0
    return discount_type, float(value)


def _decorate_name(name: str, variant, size_pack) -> str:
    """Separate variant rows with the contract's `Base — Variant / Size` form."""
    parts = [part for part in (_cell_text(variant), _cell_text(size_pack)) if part]
    if not parts:
        return name
    return f"{name} — {' / '.join(parts)}"


def _build_description(values: dict) -> str | None:
    """Encode extra catalogue metadata in the existing description column."""
    parts: list[str] = []
    for key, label in (
        ("brand", "Brand"),
        ("category", "Category"),
        ("subcategory", "Subcategory"),
        ("variant", "Variant"),
        ("size_pack", "Size"),
        ("barcode_type", "Barcode Type"),
    ):
        value = _cell_text(values.get(key))
        if value:
            parts.append(f"{label}: {value}")
    return " | ".join(parts) or None


def _generate_internal_barcode(
    db, business_id: str, used_barcodes: set[str], used_skus: set[str]
) -> tuple[str, str]:
    """Return a unique Code-128-compatible internal barcode and SKU."""
    for _ in range(100):
        barcode = "BF" + f"{secrets.randbelow(10_000_000_000):010d}"
        sku = f"SKU-{barcode}"
        if barcode in used_barcodes or sku in used_skus:
            continue
        taken = db.execute(
            select(Product.id).where(
                Product.business_id == business_id,
                (Product.barcode == barcode) | (Product.sku == sku),
            )
        ).first()
        if taken:
            continue
        used_barcodes.add(barcode)
        used_skus.add(sku)
        return barcode, sku
    raise RuntimeError("Could not generate a unique internal barcode")


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

def template_csv() -> bytes:
    """Return the official 14-column CSV template as UTF-8 bytes."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CATALOGUE_HEADER.split(","))
    for instruction in TEMPLATE_INSTRUCTIONS:
        writer.writerow([instruction] + [""] * (len(CANONICAL_COLUMNS) - 2))
    for example in TEMPLATE_EXAMPLE_ROWS:
        writer.writerow(example)
    return output.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Parsing / preview
# ---------------------------------------------------------------------------

def _table_from_csv(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader]


def _table_from_spreadsheet(content: bytes, filename: str) -> list[list[str]]:
    try:
        from openpyxl import load_workbook  # optional dependency
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ParseError(
            "Spreadsheet support is not installed on this server. Please upload a CSV file."
        ) from exc
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        if filename.lower().endswith(".xls"):
            raise ParseError(
                "Legacy .xls files are not supported. Please save as .xlsx or CSV."
            ) from exc
        raise ParseError(f"Could not read the spreadsheet: {exc}") from exc
    try:
        sheet = workbook.active
        table: list[list[str]] = []
        for row in sheet.iter_rows(values_only=True):
            table.append(["" if cell is None else str(cell) for cell in row])
        return table
    finally:
        workbook.close()


def parse_file(
    filename: str,
    content: bytes,
    default_gst_rate: float = 18.0,
    db=None,
    business_id: str | None = None,
) -> dict:
    """Parse an uploaded file into a preview dictionary (see contract)."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    name = (filename or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        table = _table_from_csv(content)
    elif name.endswith(".xlsx") or name.endswith(".xlsm") or name.endswith(".xls"):
        table = _table_from_spreadsheet(content, filename)
    else:
        raise ParseError("Unsupported file type. Upload a .csv, .xlsx or .xls file.")

    if not table:
        raise ParseError("The file is empty.")

    header = table[0]
    recognized: dict[str, str | None] = {column: None for column in CANONICAL_COLUMNS}
    index_by_column: dict[str, int] = {}
    unsupported: list[str] = []
    for idx, raw_header in enumerate(header):
        canonical = _ALIAS_LOOKUP.get(_normalize_header(raw_header))
        if canonical and canonical not in index_by_column:
            index_by_column[canonical] = idx
            recognized[canonical] = str(raw_header).strip()
        elif str(raw_header).strip():
            unsupported.append(str(raw_header).strip())

    base_gst = default_gst_rate if default_gst_rate is not None else 18.0
    rows: list[dict] = []
    seen_barcodes: dict[str, int] = {}
    error_count = 0

    for row_number, raw_row in enumerate(table[1:], start=2):
        def cell(column: str) -> str:
            idx = index_by_column.get(column)
            return _cell_text(raw_row[idx]) if idx is not None and idx < len(raw_row) else ""

        name_value = cell("name")
        if all(not _cell_text(v) for v in raw_row):
            continue
        if name_value.startswith("#"):
            continue

        errors: list[str] = []
        warnings: list[str] = []
        if not name_value:
            errors.append("Product name is required")

        selling, selling_ok, selling_provided = _number(cell("selling_price"))
        if not selling_provided:
            errors.append("Selling price is required")
        elif not selling_ok:
            errors.append("Selling price must be a number")
        elif selling is not None and selling < 0:
            errors.append("Selling price cannot be negative")

        cost, cost_ok, cost_provided = _number(cell("cost_price"))
        if cost_provided and not cost_ok:
            errors.append("Cost price must be a number")
        elif cost is not None and cost < 0:
            errors.append("Cost price cannot be negative")

        quantity, quantity_ok, quantity_provided = _number(cell("quantity"))
        if quantity_provided and not quantity_ok:
            errors.append("Quantity must be a number")
        elif quantity is not None and quantity < 0:
            errors.append("Quantity cannot be negative")
        if not quantity_provided:
            quantity = 0.0

        gst, gst_ok, gst_provided = _number(cell("gst_rate"))
        if gst_provided and not gst_ok:
            errors.append("GST rate must be a number")
        elif gst is not None and not (0 <= gst <= 100):
            errors.append("GST rate must be between 0 and 100")
        if not gst_provided:
            gst = float(base_gst)

        discount_type, discount_value = _validate_discount(
            cell("discount_type"), cell("discount_value"), errors
        )
        raw_barcode_type = _normalize_barcode_type(cell("barcode_type"))
        if raw_barcode_type and raw_barcode_type not in {
            "manufacturer", "internal"
        }:
            warnings.append(
                f"Unknown barcode type '{raw_barcode_type}'; it will be treated "
                "as a manufacturer barcode"
            )

        barcode = _normalize_barcode(cell("barcode"))
        if barcode:
            first_row = seen_barcodes.get(barcode)
            if first_row is not None:
                # A barcode can only belong to one product. Surface this as an
                # error so the owner can fix it in the editable preview instead
                # of having the row silently skipped at commit time.
                errors.append(
                    f"Duplicate barcode '{barcode}' also appears on row {first_row}"
                )
            else:
                seen_barcodes[barcode] = row_number
            if db is not None and business_id:
                existing = db.execute(
                    select(Product.id, Product.name).where(
                        Product.business_id == business_id, Product.barcode == barcode
                    )
                ).first()
                if existing:
                    warnings.append(
                        f"Barcode '{barcode}' already belongs to product "
                        f"'{existing.name}' (id {existing.id})"
                    )

        rows.append(
            {
                "row_number": row_number,
                "name": name_value,
                "brand": cell("brand") or None,
                "category": cell("category") or None,
                "subcategory": cell("subcategory") or None,
                "variant": cell("variant") or None,
                "size_pack": cell("size_pack") or None,
                "barcode": barcode,
                "barcode_type": raw_barcode_type,
                "sku": cell("sku") or None,
                "cost_price": cost if cost_provided and cost_ok else None,
                "selling_price": selling if selling_ok and selling_provided else None,
                "discount_type": discount_type,
                "discount_value": discount_value,
                "quantity": quantity if quantity_ok and quantity is not None else 0,
                "gst_rate": gst if gst_ok and gst is not None else float(base_gst),
                "errors": errors,
                "warnings": warnings,
                "valid": not errors,
            }
        )
        if errors:
            error_count += 1

    return {
        "recognized_columns": recognized,
        "unsupported_columns": unsupported,
        "total_rows": len(rows),
        "error_count": error_count,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------

def _get(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _validated_values(row, default_gst_rate: float) -> tuple[dict | None, str | None]:
    """Validate one commit row, returning normalized values or an error."""
    name = str(_get(row, "name", "") or "").strip()
    if not name:
        return None, "Name is required"

    selling, selling_ok, selling_provided = _number(_get(row, "selling_price"))
    if not selling_provided:
        return None, "Selling price is required"
    if not selling_ok or selling is None:
        return None, "Selling price must be a number"
    if selling < 0:
        return None, "Selling price cannot be negative"

    cost, cost_ok, cost_provided = _number(_get(row, "cost_price"))
    if cost_provided and (not cost_ok or cost is None):
        return None, "Cost price must be a number"
    if cost is not None and cost < 0:
        return None, "Cost price cannot be negative"

    quantity, quantity_ok, quantity_provided = _number(_get(row, "quantity"))
    if not quantity_provided:
        quantity = 0.0
    if not quantity_ok or quantity is None:
        return None, "Quantity must be a number"
    if quantity < 0:
        return None, "Quantity cannot be negative"

    raw_gst = _get(row, "gst_rate")
    gst, gst_ok, gst_provided = _number(raw_gst)
    if raw_gst is None or not gst_provided:
        gst = float(default_gst_rate if default_gst_rate is not None else 18.0)
    elif not gst_ok or gst is None:
        return None, "GST rate must be a number"
    if gst is None or not (0 <= gst <= 100):
        return None, "GST rate must be between 0 and 100"

    barcode = _normalize_barcode(_get(row, "barcode"))
    barcode_type = _normalize_barcode_type(_get(row, "barcode_type"))
    if barcode_type not in {"manufacturer", "internal"}:
        # A real printed barcode is always a manufacturer barcode; internal is
        # reserved for barcodes generated by BillFlow.
        barcode_type = "manufacturer" if barcode else None

    errors: list[str] = []
    discount_type, discount_value = _validate_discount(
        _get(row, "discount_type"), _get(row, "discount_value"), errors
    )
    if errors:
        return None, errors[0]

    return {
        "name": _decorate_name(
            name, _get(row, "variant"), _get(row, "size_pack")
        ),
        "base_name": name,
        "brand": _cell_text(_get(row, "brand")) or None,
        "category": _cell_text(_get(row, "category")) or None,
        "subcategory": _cell_text(_get(row, "subcategory")) or None,
        "variant": _cell_text(_get(row, "variant")) or None,
        "size_pack": _cell_text(_get(row, "size_pack")) or None,
        "barcode": barcode,
        "barcode_type": barcode_type,
        "sku": _cell_text(_get(row, "sku")) or None,
        "cost_price": cost if cost_provided else None,
        "selling_price": selling,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "quantity": quantity,
        "gst_rate": gst,
    }, None


def _find_existing(db, business_id: str, values: dict) -> tuple[Product | None, str | None]:
    """Match by barcode first, then by exact name when barcode is absent.

    Returns (product, error). More than one match is ambiguous and skipped.
    """
    barcode = values["barcode"]
    if barcode:
        matches = list(
            db.execute(
                select(Product).where(
                    Product.business_id == business_id, Product.barcode == barcode
                )
            ).scalars().all()
        )
    else:
        matches = list(
            db.execute(
                select(Product).where(
                    Product.business_id == business_id,
                    func.lower(Product.name) == values["name"].lower(),
                )
            ).scalars().all()
        )

    if len(matches) > 1:
        return None, "Ambiguous match: multiple products match this row; skipped"
    return (matches[0] if matches else None), None


def commit_rows(
    db,
    business_id: str,
    user_id: str | None,
    rows,
    overwrite_stock: bool = False,
    default_gst_rate: float = 18.0,
) -> dict:
    """Commit a batch of validated rows in one transaction.

    Invalid/ambiguous rows are skipped with an error. A database failure rolls
    the entire batch back. The caller's request session performs the final
    commit (see ``get_db``).
    """
    result: dict = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "stock_movements": 0,
        "activity_entries": 0,
    }
    gst_default = (
        float(default_gst_rate) if default_gst_rate is not None else 18.0
    )
    # Barcodes/SKUs generated in this batch must not collide with each other or
    # with anything already present in the tenant.
    used_barcodes: set[str] = set()
    used_skus: set[str] = set()
    seen_explicit_barcodes: dict[str, int] = {}

    try:
        for offset, row in enumerate(rows):
            row_number = offset + 1
            values, error = _validated_values(row, gst_default)
            if error:
                result["errors"].append({"row": row_number, "message": error})
                result["skipped"] += 1
                continue

            explicit_barcode = values["barcode"]
            if explicit_barcode:
                first_row = seen_explicit_barcodes.get(explicit_barcode)
                if first_row is not None:
                    result["errors"].append(
                        {
                            "row": row_number,
                            "message": (
                                f"Duplicate barcode '{explicit_barcode}' also appears "
                                f"on row {first_row}; skipped"
                            ),
                        }
                    )
                    result["skipped"] += 1
                    continue
                seen_explicit_barcodes[explicit_barcode] = row_number
                used_barcodes.add(explicit_barcode)

            existing, match_error = _find_existing(db, business_id, values)
            if match_error:
                result["errors"].append({"row": row_number, "message": match_error})
                result["skipped"] += 1
                continue

            if existing is not None:
                if not overwrite_stock:
                    # Never silently overwrite an existing product's stock/price.
                    result["skipped"] += 1
                    continue
                before_stock = float(existing.stock)
                updated = product_service.update_product(
                    db,
                    business_id,
                    existing.id,
                    ProductUpdate(
                        stock=values["quantity"],
                        price=values["selling_price"],
                        discount_type=values["discount_type"],
                        discount_value=values["discount_value"],
                    ),
                    user_id,
                )
                after_stock = float(updated.stock)
                if abs(after_stock - before_stock) > 1e-9:
                    result["stock_movements"] += 1
                result["updated"] += 1
                result["activity_entries"] += 1
                continue

            # New product: opening stock is the imported quantity.
            barcode = values["barcode"]
            sku = values["sku"]
            sku_generated = False
            if barcode:
                # Manufacturer barcode: preserve it exactly as supplied.
                values["barcode_type"] = "manufacturer"
                if not sku:
                    sku = barcode
            else:
                barcode, generated_sku = _generate_internal_barcode(
                    db, business_id, used_barcodes, used_skus
                )
                values["barcode_type"] = "internal"
                if not sku:
                    sku = generated_sku
                    sku_generated = True
            # sku is capped at 50 chars while barcodes allow 64.
            sku = sku[:50] if sku else None
            if sku:
                if (sku in used_skus and not sku_generated) or db.execute(
                    select(Product.id).where(
                        Product.business_id == business_id, Product.sku == sku
                    )
                ).first():
                    result["errors"].append(
                        {
                            "row": row_number,
                            "message": f"SKU '{sku}' is already used by another product",
                        }
                    )
                    result["skipped"] += 1
                    continue
                used_skus.add(sku)

            data = ProductCreate(
                name=values["name"],
                sku=sku,
                barcode=barcode,
                description=_build_description(values),
                price=values["selling_price"],
                gst_rate=values["gst_rate"],
                stock=values["quantity"],
                discount_type=values["discount_type"],
                discount_value=values["discount_value"],
                track_inventory=True,
                is_service=False,
            )
            product = Product(business_id=business_id, **data.model_dump())
            db.add(product)
            db.flush()

            inventory_service.record_movement(
                db,
                business_id=business_id,
                product=product,
                quantity_change=values["quantity"],
                quantity_before=0.0,
                quantity_after=values["quantity"],
                reason="opening_stock",
                reference=product.sku,
                user_id=user_id,
                notes="Opening stock from product import",
            )
            result["stock_movements"] += 1

            entry = audit_service.log_activity(
                db,
                business_id,
                user_id=user_id,
                action="product.create",
                category="product",
                reference=product.sku or product.barcode or product.name,
                entity_type="product",
                entity_id=product.id,
                details={
                    "name": product.name,
                    "barcode": product.barcode,
                    "stock": float(product.stock),
                    "source": "import",
                },
            )
            if entry is not None:
                result["activity_entries"] += 1
            result["created"] += 1

        import_entry = audit_service.log_activity(
            db,
            business_id,
            user_id=user_id,
            action="product.import",
            category="product",
            reference="product-import",
            entity_type="product",
            details={
                "created": result["created"],
                "updated": result["updated"],
                "skipped": result["skipped"],
                "errors": len(result["errors"]),
            },
        )
        if import_entry is not None:
            result["activity_entries"] += 1
    except Exception:
        # One bad row must not leave a half-imported batch behind.
        db.rollback()
        raise

    return result


# ---------------------------------------------------------------------------
# Barcode label sheets
# ---------------------------------------------------------------------------

def _barcode_marker(product: Product) -> str:
    """Distinguish owner-printed manufacturer codes from BillFlow internal ones."""
    description = (product.description or "").lower()
    if "barcode type: internal" in description:
        return "INTERNAL"
    if (product.barcode or "").startswith("BF") and (product.sku or "").startswith(
        "SKU-BF"
    ):
        return "INTERNAL"
    return "MANUFACTURER"


def _label_text(value, max_length: int = 60) -> str:
    """Keep product text renderable with reportlab's built-in Helvetica font."""
    text = str(value or "").encode("latin-1", "replace").decode("latin-1")
    return text[:max_length]


def barcode_labels_pdf(products: list[Product]) -> bytes:
    """Build a printable Code 128 label sheet for the given products."""
    from reportlab.graphics.barcode.code128 import Code128
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("BillFlow product barcode labels")
    page_width, page_height = A4
    left_margin = 34.0
    columns = 2
    label_width = (page_width - 2 * left_margin) / columns
    label_height = 124.0
    top = page_height - left_margin
    y = top - label_height
    column = 0

    for product in products:
        if y < left_margin:
            pdf.showPage()
            y = top - label_height
            column = 0
        x = left_margin + column * label_width

        pdf.setLineWidth(0.6)
        pdf.roundRect(
            x, y, label_width - 8, label_height - 8, 4, stroke=1, fill=0
        )
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(x + 10, y + label_height - 24, _label_text(product.name, 42))
        pdf.setFont("Helvetica", 8)
        pdf.drawString(
            x + 10,
            y + label_height - 38,
            f"SKU: {_label_text(product.sku or '-', 32)}",
        )

        value = str(product.barcode or product.sku or product.id)
        try:
            symbol = Code128(value, barHeight=34, barWidth=0.6)
            symbol.drawOn(pdf, x + 10, y + 42)
        except Exception:  # an unexpected value must not break the whole sheet
            pdf.setFont("Helvetica", 8)
            pdf.drawString(x + 10, y + 52, _label_text(value, 40))

        pdf.setFont("Helvetica", 9)
        pdf.drawCentredString(x + label_width / 2 - 4, y + 31, _label_text(value, 34))
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawCentredString(
            x + label_width / 2 - 4, y + 16, _barcode_marker(product)
        )

        column += 1
        if column >= columns:
            column = 0
            y -= label_height

    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Barcode lookup
# ---------------------------------------------------------------------------

def lookup_barcode(barcode: str) -> dict:
    """Look up a barcode in the public Open Food Facts v2 catalogue."""
    safe_barcode = quote(str(barcode or "").strip(), safe="")
    url = (
        "https://world.openfoodfacts.org/api/v2/product/"
        f"{safe_barcode}.json?fields=product_name,brands,categories,image_url"
    )
    base = {
        "found": False,
        "source": "none",
        "barcode": barcode,
        "price": None,
        "message": "",
    }
    try:
        response = httpx.get(url, timeout=8.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # network error, timeout or bad payload
        logger.info("Barcode catalogue lookup failed for %s: %s", barcode, exc)
        return {**base, "message": f"Catalogue lookup unavailable: {exc}"}

    product = payload.get("product") if isinstance(payload, dict) else None
    if not product or payload.get("status") == 0:
        return {
            **base,
            "source": "openfoodfacts",
            "message": "Product not found in the catalogue.",
        }

    def field(key: str):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    name = field("product_name") or field("product_name_generic")
    return {
        "found": True,
        "source": "openfoodfacts",
        "barcode": barcode,
        "name": name,
        "brand": field("brands"),
        "category": field("categories"),
        "image_url": field("image_url"),
        "price": None,
        "message": (
            "Found in Open Food Facts. Verify the details and add your own price "
            "before importing."
        ),
    }


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

_QUANTITY_PATTERNS = [
    # "Qty 5", "Qty: 5", "quantity 5"
    re.compile(r"\b(?:qty|quantity)\s*[:=-]?\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE),
    # trailing "2 pcs", "3 units", "5 nos"
    re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(?:pcs?|pieces?|units?|nos?|items?)\b\.?\s*$",
        re.IGNORECASE,
    ),
    # "x3", "x 3" at word boundary (but not inside a word like "max 3")
    re.compile(r"(?:^|\s)x\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE),
]


def _parse_ocr_line(raw_line: str, confidence: float) -> dict:
    """Conservatively turn a single OCR line into a name + optional quantity."""
    line = raw_line.strip()
    quantity: float | None = None
    name_source = line
    for pattern in _QUANTITY_PATTERNS:
        match = pattern.search(name_source)
        if match:
            try:
                quantity = float(match.group(1))
            except (TypeError, ValueError):
                quantity = None
            name_source = (name_source[: match.start()] + " " + name_source[match.end():]).strip()
            break

    # Tidy up leftover separators/bullets without inventing content.
    name = re.sub(r"^[\s\-•*·:]+", "", name_source).strip()
    name = re.sub(r"\s{2,}", " ", name)
    name = name.strip(" ,;-|:.").strip()

    uncertain: list[str] = []
    score = max(0.0, min(1.0, confidence))

    if not name:
        uncertain.append("name")
        score = min(score, 0.25)
    if quantity is None:
        uncertain.append("quantity")
        score = min(score, 0.55)
    if confidence < 0.6:
        score = min(score, confidence)
        if "name" not in uncertain:
            uncertain.append("name")

    return {
        "name": name,
        "quantity": quantity,
        "confidence": round(score, 2),
        "uncertain_fields": uncertain,
        "raw_line": raw_line,
    }


def _pdf_text(content: bytes) -> str:
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OcrUnavailable(OCR_UNAVAILABLE_MESSAGE) from exc
    except Exception as exc:  # pragma: no cover - unusual subprocess failure
        raise OcrUnavailable(OCR_UNAVAILABLE_MESSAGE) from exc
    if completed.returncode != 0 and not completed.stdout:
        raise OcrUnavailable(OCR_UNAVAILABLE_MESSAGE)
    return completed.stdout.decode("utf-8", errors="replace")


def _image_lines(content: bytes, filename: str) -> list[tuple[str, float]]:
    try:
        import pytesseract  # optional dependency, imported lazily
        from PIL import Image
    except ImportError as exc:
        raise OcrUnavailable(OCR_UNAVAILABLE_MESSAGE) from exc

    try:
        image = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise ParseError(
            "Could not read the image file. Upload a valid PNG, JPG, JPEG or WebP."
        ) from exc
    try:
        data = pytesseract.image_to_data(
            image, output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        message = str(exc).lower()
        if (
            "tesseract" in message
            or "not found" in message
            or "no such file" in message
            or "not installed" in message
        ):
            raise OcrUnavailable(OCR_UNAVAILABLE_MESSAGE) from exc
        raise

    # Group recognised words into lines with an averaged confidence.
    grouped: dict[tuple, tuple[list[str], list[float]]] = {}
    for idx, text in enumerate(data.get("text", [])):
        word = str(text).strip()
        if not word:
            continue
        try:
            word_conf = float(data["conf"][idx])
        except (IndexError, TypeError, ValueError):
            word_conf = 0.0
        if word_conf < 0:
            continue
        key = (
            data["block_num"][idx],
            data["par_num"][idx],
            data["line_num"][idx],
        )
        words, confs = grouped.setdefault(key, ([], []))
        words.append(word)
        confs.append(word_conf)

    lines: list[tuple[str, float]] = []
    for key in sorted(grouped):
        words, confs = grouped[key]
        avg = sum(confs) / len(confs) if confs else 0.0
        lines.append((" ".join(words), avg / 100.0))
    return lines


def ocr_extract(filename: str, content: bytes) -> dict:
    """Extract conservative name/quantity rows from an image or PDF."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    name = (filename or "").lower()
    is_pdf = name.endswith(".pdf")
    is_image = name.endswith((".png", ".jpg", ".jpeg", ".webp"))
    if not is_pdf and not is_image:
        raise ParseError("Unsupported file type for OCR. Upload an image or PDF.")

    if is_pdf:
        lines = [
            (line, 0.95)
            for line in _pdf_text(content).splitlines()
            if line.strip()
        ]
        source = "pdftotext"
    else:
        lines = _image_lines(content, filename)
        source = "tesseract"

    parsed = [_parse_ocr_line(line, confidence) for line, confidence in lines]
    parsed = [row for row in parsed if row["name"] or row["quantity"] is not None]

    warnings: list[str] = []
    low_confidence = sum(1 for row in parsed if row["confidence"] < 0.6)
    missing_qty = sum(1 for row in parsed if "quantity" in row["uncertain_fields"])
    if low_confidence:
        warnings.append(
            f"{low_confidence} row(s) have low OCR confidence — review them before importing."
        )
    if missing_qty:
        warnings.append(
            f"Opening stock could not be read for {missing_qty} row(s); set it manually."
        )
    if not parsed:
        warnings.append("No product rows could be read from this document.")

    return {"rows": parsed, "source": source, "warnings": warnings}
