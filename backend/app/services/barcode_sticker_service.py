"""Barcode Sticker Studio: tenant-safe barcode assignment and sticker printing.

This feature is deliberately additive: it reuses ``products.barcode`` and
writes generated codes through ``product_service.update_product`` so the normal
audit trail is preserved. Stock, price and SKU are never touched.
"""

from __future__ import annotations

import io
import math
import secrets
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import Drawing, Group, Rect, String
from reportlab.lib.colors import black, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.models.product import Product
from app.schemas.product import ProductUpdate
from app.services import product_service


class ValidationError(Exception):
    """Raised for invalid sticker sizes, quantities or layouts."""


class NotFoundError(Exception):
    """Raised when a requested product does not belong to the tenant."""


# 1 mm = 72 / 25.4 points. Decimals keep the sheet arithmetic exact.
MM_TO_PT = Decimal(72) / Decimal("25.4")
A4_WIDTH_MM = Decimal("210")
A4_HEIGHT_MM = Decimal("297")
SHEET_MARGIN_MM = Decimal("8")
SHEET_GAP_MM = Decimal("3")
MAX_DIMENSION_MM = Decimal("300")
MAX_TOTAL_STICKERS = 5000

SIZES: dict[str, tuple[Decimal, Decimal]] = {
    "small": (Decimal("40"), Decimal("25")),
    "medium": (Decimal("50"), Decimal("30")),
    "large": (Decimal("60"), Decimal("40")),
    "xl": (Decimal("100"), Decimal("50")),
}
LAYOUTS = ("sheet", "individual")


def _pt(mm: Decimal | float | int) -> float:
    """Convert millimetres to PostScript points."""
    return float((Decimal(str(mm)) if not isinstance(mm, Decimal) else mm) * MM_TO_PT)


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"{label} must be a positive number") from exc
    if not number.is_finite():
        raise ValidationError(f"{label} must be a finite number")
    return number


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        pid = str(value)
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _load_products(db, business_id: str, product_ids: list[str]) -> dict[str, Product]:
    if not product_ids:
        return {}
    rows = db.execute(
        select(Product).where(
            Product.business_id == business_id, Product.id.in_(product_ids)
        )
    ).scalars().all()
    return {product.id: product for product in rows}


def ensure_barcodes(
    db,
    business_id: str,
    product_ids: Iterable[str],
    user_id: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Guarantee every requested product has a barcode.

    Returns ``(barcodes_by_product_id, generated_product_ids)``. Existing
    barcodes are reused byte-for-byte; only blank ones get a fresh ``BF`` +
    10 digit internal code, checked against every barcode in the tenant and
    saved through ``product_service.update_product`` (which audits the change
    without touching stock, price or SKU).
    """
    ids = _unique(product_ids)
    products = _load_products(db, business_id, ids)
    missing = [pid for pid in ids if pid not in products]
    if missing:
        raise NotFoundError("Product not found: " + ", ".join(missing))

    taken = {
        str(row[0])
        for row in db.execute(
            select(Product.barcode).where(
                Product.business_id == business_id, Product.barcode.is_not(None)
            )
        ).all()
        if row[0]
    }

    mapping: dict[str, str] = {}
    generated_ids: list[str] = []
    for pid in ids:
        product = products[pid]
        existing = product.barcode
        if existing is not None and str(existing).strip():
            mapping[pid] = str(existing)
            continue

        barcode = ""
        for _ in range(100):
            candidate = "BF" + f"{secrets.randbelow(10_000_000_000):010d}"
            if candidate in taken:
                continue
            taken.add(candidate)
            barcode = candidate
            break
        if not barcode:
            raise RuntimeError("Could not generate a unique internal barcode")

        product_service.update_product(
            db,
            business_id,
            pid,
            ProductUpdate(barcode=barcode),
            user_id,
        )
        mapping[pid] = barcode
        generated_ids.append(pid)

    return mapping, generated_ids


def _validate_dimensions(
    size: Any, width_mm: Any, height_mm: Any
) -> tuple[Decimal, Decimal]:
    size_key = str(size or "small").strip().lower()
    if size_key not in SIZES and size_key != "custom":
        raise ValidationError(
            "size must be one of: small, medium, large, xl, custom"
        )

    for label, raw in (("width_mm", width_mm), ("height_mm", height_mm)):
        if raw is None:
            continue
        value = _decimal(raw, label)
        if value <= 0 or value > MAX_DIMENSION_MM:
            raise ValidationError(
                f"{label} must be greater than 0 and at most 300 mm"
            )

    if size_key == "custom":
        if width_mm is None or height_mm is None:
            raise ValidationError("Custom size requires width_mm and height_mm")
        return _decimal(width_mm, "width_mm"), _decimal(height_mm, "height_mm")
    return SIZES[size_key]


def _sheet_grid(width_mm: Decimal, height_mm: Decimal) -> tuple[int, int]:
    """Columns/rows of stickers that fit on an A4 sheet (no scaling up)."""
    sticker_w, sticker_h = _pt(width_mm), _pt(height_mm)
    margin, gap = _pt(SHEET_MARGIN_MM), _pt(SHEET_GAP_MM)
    usable_w = _pt(A4_WIDTH_MM) - 2 * margin
    usable_h = _pt(A4_HEIGHT_MM) - 2 * margin
    columns = int(math.floor((usable_w + gap + 1e-9) / (sticker_w + gap)))
    rows = int(math.floor((usable_h + gap + 1e-9) / (sticker_h + gap)))
    if columns < 1 or rows < 1:
        raise ValidationError(
            "The selected sticker size does not fit on an A4 sheet with "
            "8 mm margins; use the individual layout or a smaller size"
        )
    return columns, rows


def _prepare(
    db,
    business_id: str,
    items: Any,
    size: Any,
    width_mm: Any,
    height_mm: Any,
    layout: Any,
    user_id: str | None,
) -> dict:
    """Ensure barcodes, validate options and return everything rendering needs."""
    width, height = _validate_dimensions(size, width_mm, height_mm)
    layout_key = str(layout or "sheet").strip().lower()
    if layout_key not in LAYOUTS:
        raise ValidationError("layout must be either 'sheet' or 'individual'")

    if not isinstance(items, (list, tuple)) or not items:
        raise ValidationError("At least one sticker item is required")

    quantities: dict[str, int] = {}
    for item in items:
        pid = _get(item, "product_id")
        pid = str(pid).strip() if pid is not None else ""
        if not pid:
            raise ValidationError("Every sticker item needs a product_id")
        raw_quantity = _get(item, "quantity", 1)
        if isinstance(raw_quantity, bool):
            raise ValidationError("quantity must be an integer of at least 1")
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError) as exc:
            raise ValidationError("quantity must be an integer of at least 1") from exc
        if raw_quantity is None or quantity != raw_quantity or quantity < 1:
            raise ValidationError("quantity must be an integer of at least 1")
        quantities[pid] = quantities.get(pid, 0) + quantity

    total = sum(quantities.values())
    if total > MAX_TOTAL_STICKERS:
        raise ValidationError(
            f"Too many stickers: {total}. The maximum is {MAX_TOTAL_STICKERS}."
        )

    mapping, _ = ensure_barcodes(db, business_id, list(quantities), user_id)
    products = _load_products(db, business_id, list(quantities))
    prepared_items = [
        {
            "product_id": pid,
            "name": str(products[pid].name or ""),
            "barcode": mapping[pid],
            "quantity": quantity,
        }
        for pid, quantity in quantities.items()
    ]

    columns, rows = (1, 1) if layout_key == "individual" else _sheet_grid(width, height)
    capacity = columns * rows
    return {
        "items": prepared_items,
        "total_stickers": total,
        "pages": max(1, math.ceil(total / capacity)),
        "width_mm": float(width),
        "height_mm": float(height),
        "layout": layout_key,
        "columns": columns,
        "rows": rows,
        "capacity": capacity,
    }


# ---------------------------------------------------------------------------
# Sticker rendering
# ---------------------------------------------------------------------------

def _valid_ean13(value: str) -> bool:
    """True only for a 13-digit EAN with a correct GS1 check digit."""
    if len(value) != 13 or not value.isdigit():
        return False
    total = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(value[:12])
    )
    return (10 - total % 10) % 10 == int(value[12])


def _latin1(value: str) -> str:
    """reportlab's built-in fonts cannot render non-Latin-1 characters."""
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


def _fit_text(value: str, font: str, size: float, max_width: float) -> str:
    text = " ".join(_latin1(value).split())
    if not text:
        return ""
    if stringWidth(text, font, size) <= max_width:
        return text
    # Prefer the full value: shrink before falling back to an ellipsis.
    for candidate_size in (size, size * 0.85, size * 0.7):
        if stringWidth(text, font, candidate_size) <= max_width:
            return text
    while text and stringWidth(text + "...", font, size) > max_width:
        text = text[:-1]
    return (text + "...") if text else ""


def _barcode_widget(value: str, max_width: float, max_height: float) -> tuple[Drawing, float]:
    """Build a proportional barcode drawing plus its uniform scale factor."""
    use_ean13 = _valid_ean13(value)
    code_name = "EAN13" if use_ean13 else "Code128"
    options: dict[str, Any] = {
        "value": value[:12] if use_ean13 else _latin1(value),
        "barWidth": 1.0,
        "barHeight": 1.0,
        "humanReadable": 0,  # the number is drawn separately below the bars
    }
    if use_ean13:
        # The widget computes and prints the check digit from the first 12
        # digits; its built-in quiet zones are the GS1 11/7 module zones.
        options["quiet"] = 1
    else:
        # Ten modules of quiet zone on each side (Code 128 minimum).
        options["lquiet"] = 10
        options["rquiet"] = 10

    probe = createBarcodeDrawing(code_name, **options)
    natural_width = float(probe.width) or 1.0
    options["barHeight"] = natural_width * 0.33
    widget = createBarcodeDrawing(code_name, **options)
    scale = min(max_width / float(widget.width), max_height / float(widget.height))
    return widget, scale


def _sticker_drawing(name: str, barcode: str, width_pt: float, height_pt: float) -> Drawing:
    """A single white sticker: name on top, one barcode, number below."""
    drawing = Drawing(width_pt, height_pt)
    drawing.add(Rect(0, 0, width_pt, height_pt, fillColor=white, strokeColor=None))

    border_pad = max(0.5, min(2.0, height_pt * 0.05))
    inner_pad = border_pad + 1.5
    drawing.add(
        Rect(
            border_pad,
            border_pad,
            width_pt - 2 * border_pad,
            height_pt - 2 * border_pad,
            rx=min(3.0, height_pt * 0.08),
            ry=min(3.0, height_pt * 0.08),
            fillColor=None,
            strokeColor=black,
            strokeWidth=0.5,
        )
    )

    name_font = max(4.5, min(9.0, height_pt * 0.085))
    number_font = max(4.5, min(9.0, height_pt * 0.085))
    name_baseline = height_pt - inner_pad - name_font
    number_baseline = inner_pad

    drawing.add(
        String(
            inner_pad,
            name_baseline,
            _fit_text(name, "Helvetica-Bold", name_font, width_pt - 2 * inner_pad),
            fontName="Helvetica-Bold",
            fontSize=name_font,
            fillColor=black,
        )
    )
    drawing.add(
        String(
            width_pt / 2,
            number_baseline,
            _fit_text(barcode, "Helvetica", number_font, width_pt - 2 * inner_pad),
            fontName="Helvetica",
            fontSize=number_font,
            textAnchor="middle",
            fillColor=black,
        )
    )

    barcode_bottom = number_baseline + number_font + 2
    barcode_top = name_baseline - 3
    available_height = max(4.0, barcode_top - barcode_bottom)
    available_width = max(8.0, width_pt - 2 * inner_pad)
    widget, scale = _barcode_widget(barcode, available_width, available_height)
    scaled_w, scaled_h = float(widget.width) * scale, float(widget.height) * scale
    x = (width_pt - scaled_w) / 2
    y = barcode_bottom + (available_height - scaled_h) / 2
    group = Group(transform=[scale, 0, 0, scale, x, y])
    group.add(widget)
    drawing.add(group)
    return drawing


def _flatten(prepared: dict) -> list[dict]:
    stickers: list[dict] = []
    for item in prepared["items"]:
        stickers.extend(
            [{"name": item["name"], "barcode": item["barcode"]}] * item["quantity"]
        )
    return stickers


# ---------------------------------------------------------------------------
# Public render helpers
# ---------------------------------------------------------------------------

def build_preview(
    db,
    business_id: str,
    items: Any,
    size: str = "small",
    width_mm: float | None = None,
    height_mm: float | None = None,
    layout: str = "sheet",
    user_id: str | None = None,
) -> dict:
    """Return SVG for one real sticker plus the print job's metadata."""
    prepared = _prepare(
        db, business_id, items, size, width_mm, height_mm, layout, user_id
    )
    first = prepared["items"][0]
    drawing = _sticker_drawing(
        first["name"],
        first["barcode"],
        _pt(prepared["width_mm"]),
        _pt(prepared["height_mm"]),
    )
    return {
        "svg": renderSVG.drawToString(drawing),
        "total_stickers": prepared["total_stickers"],
        "pages": prepared["pages"],
        "width_mm": prepared["width_mm"],
        "height_mm": prepared["height_mm"],
        "layout": prepared["layout"],
        "items": prepared["items"],
    }


def build_pdf(
    db,
    business_id: str,
    items: Any,
    size: str = "small",
    width_mm: float | None = None,
    height_mm: float | None = None,
    layout: str = "sheet",
    user_id: str | None = None,
) -> bytes:
    """Render the full sticker job; sheet = A4 grid, individual = real size."""
    prepared = _prepare(
        db, business_id, items, size, width_mm, height_mm, layout, user_id
    )
    stickers = _flatten(prepared)
    width_pt, height_pt = _pt(prepared["width_mm"]), _pt(prepared["height_mm"])

    buffer = io.BytesIO()
    if prepared["layout"] == "individual":
        pdf = canvas.Canvas(buffer, pagesize=(width_pt, height_pt))
    else:
        pdf = canvas.Canvas(buffer, pagesize=(_pt(A4_WIDTH_MM), _pt(A4_HEIGHT_MM)))
    pdf.setTitle("BillFlow barcode stickers")

    if prepared["layout"] == "individual":
        for index, sticker in enumerate(stickers):
            if index:
                pdf.showPage()
            drawing = _sticker_drawing(
                sticker["name"], sticker["barcode"], width_pt, height_pt
            )
            renderPDF.draw(drawing, pdf, 0, 0)
    else:
        margin, gap = _pt(SHEET_MARGIN_MM), _pt(SHEET_GAP_MM)
        sheet_w, sheet_h = _pt(A4_WIDTH_MM), _pt(A4_HEIGHT_MM)
        columns, rows = prepared["columns"], prepared["rows"]
        used_w = columns * width_pt + (columns - 1) * gap
        used_h = rows * height_pt + (rows - 1) * gap
        origin_x = margin + (sheet_w - 2 * margin - used_w) / 2
        origin_y = margin + (sheet_h - 2 * margin - used_h) / 2
        capacity = prepared["capacity"]
        for index, sticker in enumerate(stickers):
            slot = index % capacity
            if slot == 0 and index:
                pdf.showPage()
            column, row = slot % columns, slot // columns
            x = origin_x + column * (width_pt + gap)
            y = sheet_h - origin_y - (row + 1) * height_pt - row * gap
            drawing = _sticker_drawing(
                sticker["name"], sticker["barcode"], width_pt, height_pt
            )
            renderPDF.draw(drawing, pdf, x, y)

    pdf.save()
    return buffer.getvalue()
