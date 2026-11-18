"""Orchestration for the four product-discovery tools.

This module is the only place that combines source results. It validates matches,
scores them conservatively, derives BillFlow category values and shapes the exact
14-column ``billflow_row``. It never manages inventory or invents prices/barcodes.
"""

from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any, Iterable

from . import config
from .models import (
    BILLFLOW_NOTE,
    BarcodeLookupResult,
    CategoriesResponse,
    CategoryInfo,
    ProductDetail,
    ProductRecord,
    SearchResponse,
    make_billflow_row,
)
from .sources import RawExternalProduct, SourceResponse, get_sources
from .taxonomy import (
    ALL_SOURCES,
    CATEGORIES,
    SOURCE_METADATA,
    billflow_similarity,
    category_for_source,
    normalize_category,
    select_sources,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SIZE_RE = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def _normalized(text: str) -> str:
    return " ".join(_tokens(text))


def _looks_like_barcode(query: str) -> bool:
    digits = "".join(ch for ch in str(query or "") if ch.isdigit())
    stripped = str(query or "").strip()
    return (
        stripped.isdigit()
        and config.BARCODE_MIN_DIGITS <= len(digits) <= config.BARCODE_MAX_DIGITS
    )


def _name_similarity(left: str, right: str) -> float:
    """0..1 fuzzy name match, tolerant of spelling variants (e.g. Maggi/Maggie)."""
    a, b = _normalized(left), _normalized(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    at, bt = set(a.split()), set(b.split())
    overlap = len(at & bt) / max(len(at | bt), 1)
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    substring = 0.9 if (a in b or b in a) and min(len(a), len(b)) >= 3 else 0.0
    return round(max(overlap * 0.9, seq * 0.8, substring), 4)


def _brand_agreement(given: str | None, found: str) -> bool | None:
    """True = agrees, False = disagrees, None = source has no brand evidence."""
    if given is None or not str(given).strip():
        return None
    if not str(found).strip():
        return None
    gt, ft = set(_tokens(given)), set(_tokens(found))
    if not gt:
        return None
    # agreement if any meaningful given token appears in the source brands
    for token in gt:
        if len(token) >= 2 and token in ft:
            return True
    return False


def _size_agreement(given: str | None, found: str) -> bool | None:
    """Conservative pack-size comparison. Different sizes are NEVER treated as equal."""
    if given is None or not str(given).strip():
        return None
    if not str(found).strip():
        return None
    g = _SIZE_RE.findall(str(given).lower())
    f = _SIZE_RE.findall(str(found).lower())
    if not g or not f:
        return None
    gset, fset = set(g), set(f)
    if gset.issubset(fset) or fset.issubset(gset):
        return True
    return False


def _label_to_cid(label: str) -> str | None:
    for cid, entry in CATEGORIES.items():
        if entry["billflow_category"] == label:
            return cid
    return None


def _derive_category_subcategory(
    record: RawExternalProduct, source: str, requested_category: str | None
) -> tuple[str, str]:
    label = ""
    if requested_category:
        cid = normalize_category(requested_category)
        if cid:
            label = CATEGORIES[cid]["billflow_category"]
    if not label:
        for tag in record.categories_tags:
            found = billflow_similarity(tag)
            if found:
                label = found
                break
    if not label:
        label = billflow_similarity(record.categories)
    if not label:
        label = category_for_source(source)

    parts = [p.strip() for p in record.categories.split(",") if p.strip()]
    subcategory = parts[-1][:60] if parts else ""
    cid = _label_to_cid(label)
    if cid:
        haystack = _normalized(record.categories + " " + " ".join(record.categories_tags))
        for known in CATEGORIES[cid]["subcategories"]:
            if _normalized(known) and _normalized(known) in haystack:
                subcategory = known
                break
    return label, subcategory


def _confidence(
    record: RawExternalProduct,
    *,
    query: str,
    brand: str | None,
    requested_category: str | None,
    source: str,
    barcode_query: bool = False,
) -> float:
    if barcode_query:
        return 1.0
    score = _name_similarity(query, record.product_name)
    if _brand_agreement(brand, record.brands) is True:
        score += 0.05
    if requested_category and normalize_category(requested_category):
        score += 0.02
    # Records with a real pack size are more useful onboarding leads.
    if record.quantity:
        score += 0.02
    return round(min(score, 1.0), 4)


def _shape_product(
    record: RawExternalProduct,
    *,
    source: str,
    requested_category: str | None,
    confidence: float,
    barcode_status: str = "verified",
) -> ProductRecord:
    category, subcategory = _derive_category_subcategory(record, source, requested_category)
    metadata = SOURCE_METADATA.get(source, {})
    source_url = f"https://{metadata.get('host', '')}/product/{record.code}" if metadata else ""
    notes = "Barcode comes from the external catalogue record for this exact product."
    if barcode_status != "verified":
        notes = "No verified manufacturer barcode is available; BillFlow will generate an internal one."
    return ProductRecord(
        product_name=record.product_name,
        brand=record.brands,
        category=category,
        subcategory=subcategory,
        size_pack=record.quantity,
        variant=record.variant,
        barcode=record.code if barcode_status == "verified" else "",
        barcode_status=barcode_status,
        source=source,
        source_url=source_url,
        confidence=confidence,
        billflow_row=make_billflow_row(
            product_name=record.product_name,
            brand=record.brands,
            category=category,
            subcategory=subcategory,
            variant=record.variant,
            size_pack=record.quantity,
            barcode=record.code if barcode_status == "verified" else "",
            barcode_type="manufacturer" if barcode_status == "verified" else "internal",
        ),
        notes=notes,
    )


def _dedupe(products: Iterable[ProductRecord]) -> list[ProductRecord]:
    """Keep the best-scoring record per barcode; drop nameless records."""
    best: dict[str, ProductRecord] = {}
    for product in products:
        if not product.product_name.strip():
            continue
        key = product.barcode or f"__{product.product_name.lower()}|{product.source}"
        existing = best.get(key)
        if existing is None or product.confidence > existing.confidence:
            best[key] = product
    return list(best.values())


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


async def _gather(coro_list: list[Any]) -> list[Any]:
    """Run adapter calls concurrently, converting unexpected errors into warnings."""
    if not coro_list:
        return []
    return await asyncio.gather(*coro_list, return_exceptions=True)


def _warning_from_exception(source: str, exc: BaseException) -> str:
    return f"{source}: adapter error ({type(exc).__name__}: {exc}); skipped."


# --------------------------------------------------------------------------- #
# public tool implementations                                                  #
# --------------------------------------------------------------------------- #

def get_categories() -> CategoriesResponse:
    categories = [
        CategoryInfo(
            id=cid,
            label=entry["label"],
            description=entry["description"],
            subcategories=list(entry["subcategories"]),
            sources=list(entry["sources"]),
            coverage_caveat=entry["coverage_caveat"],
            billflow_category=entry["billflow_category"],
        )
        for cid, entry in CATEGORIES.items()
    ]
    return CategoriesResponse(
        categories=categories,
        warnings=[
            "Coverage caveats are advisory; always review discovered rows before import.",
            "No source provides reliable prices, discounts or stock levels.",
        ],
    )


async def search_products(
    query: str,
    category: str | None = None,
    brand: str | None = None,
    page_size: int = 20,
) -> SearchResponse:
    query = str(query or "").strip()
    if not query:
        return SearchResponse(
            warnings=["Empty query: nothing to search."],
            count=0,
            category=category,
            brand=brand,
        )

    source_names_to_query, warnings = select_sources(category, query)
    sources = get_sources(source_names_to_query)
    queried = [s.name for s in sources]
    barcode_query = _looks_like_barcode(query)

    if not sources:
        return SearchResponse(
            sources_queried=[],
            warnings=warnings
            + ["No reliable public catalogue for this category; no products searched."],
            count=0,
            query=query,
            category=category,
            brand=brand,
        )

    if barcode_query:
        tasks = [s.get_by_barcode(query) for s in sources]
    else:
        tasks = [
            s.search(query, brand=brand, category=category, page_size=page_size)
            for s in sources
        ]
    responses = await _gather(tasks)

    shaped: list[ProductRecord] = []
    all_warnings: list[str] = list(warnings)
    any_available = False
    for response in responses:
        if isinstance(response, BaseException):
            all_warnings.append(_warning_from_exception("source", response))
            continue
        if not isinstance(response, SourceResponse):
            continue
        all_warnings.extend(response.warnings)
        if response.available:
            any_available = True
        for record in response.products:
            confidence = _confidence(
                record,
                query=query,
                brand=brand,
                requested_category=category,
                source=response.source,
                barcode_query=barcode_query,
            )
            shaped.append(
                _shape_product(
                    record,
                    source=response.source,
                    requested_category=category,
                    confidence=confidence,
                )
            )

    products = sorted(_dedupe(shaped), key=lambda p: p.confidence, reverse=True)
    products = products[: max(1, min(int(page_size), 100))]

    if not products:
        all_warnings.append(
            "No validated products found in the queried catalogues for this query."
            if any_available
            else "All sources were unreachable; no products could be verified."
        )
        if category and normalize_category(category):
            caveat = CATEGORIES[normalize_category(category)]["coverage_caveat"]
            if caveat not in all_warnings:
                all_warnings.append(f"Coverage caveat for {category!r}: {caveat}")
    if not any_available:
        all_warnings.append("Graceful degradation: sources did not respond; results may be incomplete.")

    return SearchResponse(
        products=products,
        sources_queried=_unique(queried),
        warnings=_unique(all_warnings),
        count=len(products),
        query=query,
        category=category,
        brand=brand,
    )


async def get_product_details(
    barcode: str | None = None,
    product_id: str | None = None,
    source: str | None = None,
) -> ProductDetail:
    empty_row = make_billflow_row()
    if not barcode and not product_id:
        return ProductDetail(
            error="barcode or product_id is required; no product was looked up.",
            notes=BILLFLOW_NOTE + " No identifier was provided, so nothing was fabricated.",
            billflow_row=empty_row,
        )

    raw_id = str(barcode or product_id or "").strip()
    source_key = str(source or "").strip().lower() or None
    if ":" in raw_id and not barcode:
        maybe_source, _, maybe_code = raw_id.partition(":")
        if maybe_source.strip().lower() in ALL_SOURCES:
            source_key = source_key or maybe_source.strip().lower()
            raw_id = maybe_code.strip()
    code = "".join(ch for ch in raw_id if ch.isdigit())
    if not code:
        return ProductDetail(
            error=f"Invalid product identifier {raw_id!r}: no numeric barcode found.",
            notes=BILLFLOW_NOTE,
            billflow_row=empty_row,
        )

    if source_key:
        selected = get_sources([source_key])
        if not selected:
            return ProductDetail(
                error=f"Unknown source {source_key!r}.",
                notes=BILLFLOW_NOTE,
                billflow_row=empty_row,
            )
    else:
        selected = get_sources(ALL_SOURCES)

    responses = await _gather([s.get_by_barcode(code) for s in selected])
    warnings: list[str] = []
    queried_urls: list[str] = []
    found_record: RawExternalProduct | None = None
    found_source = ""
    raw_evidence: dict[str, Any] = {}
    for response in responses:
        if isinstance(response, BaseException):
            warnings.append(_warning_from_exception("source", response))
            continue
        if not isinstance(response, SourceResponse):
            continue
        warnings.extend(response.warnings)
        queried_urls.extend(response.queried_urls)
        if response.raw_evidence and not raw_evidence:
            raw_evidence = response.raw_evidence
        if found_record is None and response.products:
            found_record = response.products[0]
            found_source = response.source

    evidence: dict[str, Any] = {
        "requested_identifier": raw_id,
        "requested_source": source_key or "all",
        "queried_urls": _unique(queried_urls),
        "warnings": _unique(warnings),
    }
    if raw_evidence:
        evidence.update(raw_evidence)

    if found_record is None:
        return ProductDetail(
            manufacturer_barcode="",
            barcode_status="not_found",
            source=source_key or "none",
            raw_evidence=evidence,
            notes=BILLFLOW_NOTE
            + " No catalogue record matched this barcode; no fields were invented."
            + (" " + " ".join(_unique(warnings)) if warnings else ""),
            billflow_row=empty_row,
            found=False,
        )

    category, subcategory = _derive_category_subcategory(found_record, found_source, None)
    metadata = SOURCE_METADATA.get(found_source, {})
    source_url = (
        f"https://{metadata.get('host', '')}/product/{found_record.code}" if metadata else ""
    )
    evidence.update(
        {
            "code": found_record.code,
            "product_name_raw": found_record.product_name,
            "brands_raw": found_record.brands,
            "categories_raw": found_record.categories,
            "categories_tags": found_record.categories_tags,
            "quantity_raw": found_record.quantity,
            "image_url": found_record.image_url,
        }
    )
    return ProductDetail(
        product_name=found_record.product_name,
        brand=found_record.brands,
        category=category,
        subcategory=subcategory,
        size_pack=found_record.quantity,
        variant=found_record.variant,
        manufacturer_barcode=found_record.code,
        barcode_status="verified",
        source=found_source,
        source_url=source_url,
        raw_evidence=evidence,
        notes=BILLFLOW_NOTE
        + " Barcode verified against the external catalogue record for this exact product."
        + (" " + " ".join(_unique(warnings)) if warnings else ""),
        billflow_row=make_billflow_row(
            product_name=found_record.product_name,
            brand=found_record.brands,
            category=category,
            subcategory=subcategory,
            variant=found_record.variant,
            size_pack=found_record.quantity,
            barcode=found_record.code,
            barcode_type="manufacturer",
        ),
        found=True,
    )


async def lookup_barcode(
    product_name: str,
    brand: str | None = None,
    size_pack: str | None = None,
    variant: str | None = None,
) -> BarcodeLookupResult:
    product_name = str(product_name or "").strip()
    base = BarcodeLookupResult(
        product_name=product_name,
        brand=brand or "",
        size_pack=size_pack or "",
        variant=variant or "",
        status="not_found",
        reason="No candidate could be verified from the external catalogues.",
        source="none",
        notes=BILLFLOW_NOTE,
    )
    if not product_name:
        base.reason = "product_name is required."
        return base

    # Only catalogues with plausible barcode coverage are consulted.
    sources = get_sources([s for s in ALL_SOURCES])
    responses = await _gather([s.search(product_name, page_size=25) for s in sources])
    warnings: list[str] = []
    candidates: list[tuple[float, RawExternalProduct, str, bool]] = []
    considered = 0
    any_available = False
    for response in responses:
        if isinstance(response, BaseException):
            warnings.append(_warning_from_exception("source", response))
            continue
        if not isinstance(response, SourceResponse):
            continue
        warnings.extend(response.warnings)
        if response.available:
            any_available = True
        for record in response.products:
            considered += 1
            name_score = _name_similarity(product_name, record.product_name)
            brand_ok = _brand_agreement(brand, record.brands)
            size_ok = _size_agreement(size_pack, record.quantity)
            variant_ok = _variant_agreement(variant, record.variant or record.product_name)

            brand_component = 1.0 if brand_ok is True else (0.0 if brand_ok is False else 0.5)
            size_component = 1.0 if size_ok is True else (0.0 if size_ok is False else 0.5)
            score = round(0.7 * name_score + 0.15 * brand_component + 0.15 * size_component, 4)

            strong_name = name_score >= 0.80
            # A condition that was not supplied is not a requirement; one that
            # WAS supplied must be explicitly confirmed by the catalogue record.
            brand_requirement_met = (brand_ok is True) if brand else True
            size_requirement_met = (size_ok is True) if size_pack else True
            variant_requirement_met = (variant_ok is True) if variant else True
            has_barcode = bool(record.code.strip())
            verified = (
                strong_name and brand_requirement_met and size_requirement_met
                and variant_requirement_met and has_barcode
            )
            candidates.append((score, record, response.source, verified))

    candidates.sort(key=lambda c: c[0], reverse=True)
    base.candidates_considered = considered
    base.warnings = _unique(warnings)

    if not candidates:
        base.status = "not_found"
        base.reason = (
            "All sources were unreachable; no barcode could be verified."
            if not any_available
            else "No catalogue record matched the requested product name."
        )
        if warnings:
            base.reason += " " + " ".join(_unique(warnings))
        return base

    top_score, top_record, top_source, top_verified = candidates[0]
    # Conflicting high-scoring barcodes mean the match is ambiguous - never guess.
    conflict = any(
        other[1].code != top_record.code and other[0] >= top_score - 0.05
        for other in candidates[1:6]
    )

    if top_verified and not conflict:
        category, subcategory = _derive_category_subcategory(top_record, top_source, None)
        metadata = SOURCE_METADATA.get(top_source, {})
        source_url = (
            f"https://{metadata.get('host', '')}/product/{top_record.code}" if metadata else ""
        )
        base.status = "verified"
        base.barcode = top_record.code
        base.match_score = top_score
        base.source = top_source
        base.source_url = source_url
        agreements = ["strong product-name match"]
        if brand:
            agreements.append("brand agreement")
        if size_pack:
            agreements.append("pack-size agreement")
        if variant:
            agreements.append("variant agreement")
        base.reason = (
            "Confirmed " + " + ".join(agreements)
            + " with an external catalogue record; barcode taken from that exact record."
        )
        base.product_name = top_record.product_name or product_name
        base.brand = top_record.brands or (brand or "")
        base.size_pack = top_record.quantity or (size_pack or "")
        base.billflow_row = make_billflow_row(
            product_name=base.product_name,
            brand=base.brand,
            category=category,
            subcategory=subcategory,
            size_pack=base.size_pack,
            barcode=top_record.code,
            barcode_type="manufacturer",
        )
        return base

    # Anything short of a strict verified match returns NO barcode.
    base.status = "uncertain" if top_score >= 0.55 else "not_found"
    base.match_score = top_score
    base.source = top_source if top_score >= 0.55 else "none"
    metadata = SOURCE_METADATA.get(top_source, {})
    base.source_url = (
        f"https://{metadata.get('host', '')}/product/{top_record.code}"
        if top_score >= 0.55 and metadata
        else ""
    )
    base.billflow_row = make_billflow_row(
        product_name=product_name,
        brand=brand or "",
        size_pack=size_pack or "",
        variant=variant or "",
    )
    if conflict:
        base.reason = "Multiple catalogue records with different barcodes matched; refusing to guess."
    elif not any_available:
        base.reason = "Sources were unreachable; no barcode could be verified."
    elif top_score < 0.55:
        base.reason = "Best catalogue match was too weak to trust."
    elif brand and _brand_agreement(brand, top_record.brands) is False:
        base.reason = "Brand did not agree with the best catalogue match."
    elif size_pack and _size_agreement(size_pack, top_record.quantity) is False:
        base.reason = "Pack size did not agree; barcodes are never shared across package sizes."
    elif brand and _brand_agreement(brand, top_record.brands) is None:
        base.reason = "Catalogue record lacked brand evidence; brand agreement could not be confirmed."
    elif size_pack and _size_agreement(size_pack, top_record.quantity) is None:
        base.reason = "Catalogue record lacked pack-size evidence; agreement could not be confirmed."
    else:
        base.reason = "Best match did not meet the strict verification threshold."
    if warnings:
        base.reason += " " + " ".join(_unique(warnings))
    return base


def _variant_agreement(given: str | None, found: str) -> bool | None:
    if given is None or not str(given).strip():
        return None
    g, f = _normalized(given), _normalized(found)
    if not g:
        return None
    return g in f or f in g
