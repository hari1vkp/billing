"""Discovery taxonomy and source-coverage mapping.

The category ids/labels mirror BillFlow's ``GET /products/ai/categories`` contract
(grocery, general store, clothing, mobile accessories, electronics, footwear,
cosmetics, pharmacy, other) so a discovered row can be dropped into the BillFlow
14-column import template with a meaningful Category value.

This module is purely declarative: no network access happens here.
"""

from __future__ import annotations

from typing import Any

SOURCE_FOOD = "openfoodfacts"
SOURCE_BEAUTY = "openbeautyfacts"
SOURCE_PRODUCTS = "openproductsfacts"
ALL_SOURCES = (SOURCE_FOOD, SOURCE_BEAUTY, SOURCE_PRODUCTS)

# id -> BillFlow-aligned taxonomy entry.
CATEGORIES: dict[str, dict[str, Any]] = {
    "grocery": {
        "label": "Grocery & Staples",
        "description": "Kirana/supermarket goods: staples, snacks, beverages, household consumables.",
        "subcategories": [
            "Staples", "Flour & Atta", "Rice", "Pulses", "Edible Oils", "Sugar & Salt",
            "Snacks & Namkeen", "Biscuits", "Breakfast Cereals", "Noodles & Pasta",
            "Beverages", "Tea & Coffee", "Dairy", "Condiments & Spices", "Frozen Foods",
            "Home Care", "Personal Care",
        ],
        "sources": [SOURCE_FOOD, SOURCE_PRODUCTS],
        "coverage_caveat": (
            "Good coverage of branded packaged food via Open Food Facts; Indian regional "
            "brands and loose/unpackaged goods are patchy. Prices are never provided."
        ),
        "billflow_category": "Grocery & Staples",
        "query_hints": ("maggi", "atta", "rice", "milk", "tea", "coffee", "biscuit", "snack", "oil", "sugar", "noodle", "beverage", "chocolate", "bread"),
    },
    "general": {
        "label": "General Store",
        "description": "Everyday household and general merchandise not tied to one vertical.",
        "subcategories": [
            "Household Supplies", "Cleaning", "Stationery", "Kitchenware", "Disposables",
            "Personal Care", "Pet Supplies", "General Merchandise",
        ],
        "sources": [SOURCE_PRODUCTS, SOURCE_FOOD],
        "coverage_caveat": (
            "Open Products Facts has moderate coverage of branded household goods; many "
            "generic/local items are absent. Barcodes are per-SKU and cannot be inferred."
        ),
        "billflow_category": "General Store",
        "query_hints": ("soap", "shampoo", "detergent", "toothpaste", "notebook", "pen", "tissue", "cleaner", "bottle"),
    },
    "clothing": {
        "label": "Clothing & Apparel",
        "description": "Men's, women's and children's garments and accessories.",
        "subcategories": [
            "T-Shirts", "Shirts", "Trousers", "Jeans", "Dresses", "Kurtas", "Innerwear",
            "Women's Wear", "Men's Wear", "Children's Wear", "Winter Wear",
        ],
        "sources": [],
        "coverage_caveat": (
            "NO RELIABLE PUBLIC SOURCE. Garments are sold per style/size/colour SKU and the "
            "Open Food Facts family catalogues do not cover apparel. Barcodes must not be "
            "guessed; BillFlow should generate internal SKUs/barcodes at import time."
        ),
        "billflow_category": "Clothing & Apparel",
        "query_hints": ("shirt", "t-shirt", "dress", "jeans", "kurta", "trouser", "apparel", "cotton shirt", "clothing"),
    },
    "mobile_accessories": {
        "label": "Mobile & Accessories",
        "description": "Phone cases, chargers, cables, screen guards and related accessories.",
        "subcategories": [
            "Cases & Covers", "Chargers", "Cables", "Screen Guards", "Power Banks",
            "Headphones", "Bluetooth Accessories", "Memory Cards",
        ],
        "sources": [SOURCE_PRODUCTS],
        "coverage_caveat": (
            "Limited, inconsistent coverage on Open Products Facts. Model-specific compatibility "
            "is often missing; never infer a barcode for an accessory variant."
        ),
        "billflow_category": "Mobile & Accessories",
        "query_hints": ("phone case", "charger", "cable", "screen guard", "power bank", "headphone", "mobile cover"),
    },
    "electronics": {
        "label": "Electronics & Appliances",
        "description": "Consumer electronics and small/large household appliances.",
        "subcategories": [
            "Small Appliances", "Large Appliances", "Audio", "Cameras", "Computing",
            "Lighting", "Fans", "Kitchen Appliances", "Personal Electronics",
        ],
        "sources": [SOURCE_PRODUCTS],
        "coverage_caveat": (
            "Low coverage: the Open Food Facts family catalogues are food/beauty/general-goods "
            "focused. Electronics queries commonly return zero trustworthy products. Prices and "
            "model numbers are unverified, so barcodes are only used when a catalogue record "
            "directly provides one."
        ),
        "billflow_category": "Electronics & Appliances",
        "query_hints": ("electronics", "fan", "light", "bulb", "camera", "speaker", "laptop", "appliance", "tv", "microwave"),
    },
    "footwear": {
        "label": "Footwear",
        "description": "Shoes, sandals, slippers and socks.",
        "subcategories": ["Shoes", "Sandals", "Slippers", "Sports Shoes", "Formal Shoes", "Socks"],
        "sources": [SOURCE_PRODUCTS],
        "coverage_caveat": (
            "Very low coverage. Footwear is sized per SKU; a barcode for one size/colour must "
            "never be reused for another. Expect mostly not_found barcode lookups."
        ),
        "billflow_category": "Footwear",
        "query_hints": ("shoe", "sandals", "slipper", "socks", "footwear", "sneaker"),
    },
    "cosmetics": {
        "label": "Cosmetics & Beauty",
        "description": "Beauty, skincare, haircare, fragrance and personal-care products.",
        "subcategories": [
            "Lipstick", "Lip Care", "Foundation", "Skincare", "Creams & Lotions",
            "Hair Care", "Shampoo", "Fragrance", "Nail Care", "Men's Grooming", "Soap",
        ],
        "sources": [SOURCE_BEAUTY, SOURCE_FOOD],
        "coverage_caveat": (
            "Open Beauty Facts gives reasonable coverage of branded cosmetics/toiletries, "
            "especially European brands. Indian brands and very new launches are patchy."
        ),
        "billflow_category": "Cosmetics & Beauty",
        "query_hints": ("lipstick", "cream", "foundation", "perfume", "makeup", "cosmetic", "skincare", "hair", "shampoo", "beauty", "nail"),
    },
    "pharmacy": {
        "label": "Pharmacy & Wellness",
        "description": "OTC medicines, supplements, wellness and first-aid items.",
        "subcategories": [
            "Vitamins", "Supplements", "Pain Relief", "Cold & Flu", "Digestive",
            "First Aid", "Skin Treatment", "Ayurveda", "Wellness",
        ],
        "sources": [SOURCE_BEAUTY, SOURCE_PRODUCTS],
        "coverage_caveat": (
            "No dedicated medicines catalogue exists here. Open Beauty Facts covers some "
            "wellness/derma products and Open Products Facts a few OTC items, but coverage is "
            "sparse. NEVER rely on these sources for dosage/drug facts or prescription items."
        ),
        "billflow_category": "Pharmacy & Wellness",
        "query_hints": ("vitamin", "supplement", "medicine", "tablet", "syrup", "pain relief", "ayurveda", "wellness", "bandage"),
    },
    "other": {
        "label": "Other / Mixed Business",
        "description": "Mixed retail without a single dominant vertical.",
        "subcategories": ["Mixed Goods", "Uncategorised", "Seasonal", "General Merchandise"],
        "sources": list(ALL_SOURCES),
        "coverage_caveat": (
            "All three catalogues are searched with low confidence expectations. Results are "
            "best-effort discovery leads, never authoritative product master data."
        ),
        "billflow_category": "Other / Mixed Business",
        "query_hints": (),
    },
}

# Source display metadata (used for source labels in responses).
SOURCE_METADATA: dict[str, dict[str, str]] = {
    SOURCE_FOOD: {
        "label": "Open Food Facts",
        "host": "world.openfoodfacts.org",
        "focus": "food, grocery and some household consumables",
    },
    SOURCE_BEAUTY: {
        "label": "Open Beauty Facts",
        "host": "world.openbeautyfacts.org",
        "focus": "beauty, cosmetics and personal care",
    },
    SOURCE_PRODUCTS: {
        "label": "Open Products Facts",
        "host": "world.openproductsfacts.org",
        "focus": "general/non-food consumer products",
    },
}


def normalize_category(value: str | None) -> str | None:
    """Map a free-form category id/label to a canonical taxonomy id."""
    key = " ".join(str(value or "").strip().lower().replace("_", " ").split())
    if not key:
        return None
    if key in CATEGORIES:
        return key
    aliases = {
        "grocery & staples": "grocery", "grocery and staples": "grocery", "kirana": "grocery", "food": "grocery",
        "general store": "general", "general": "general",
        "clothing & apparel": "clothing", "clothing and apparel": "clothing", "apparel": "clothing",
        "mobile & accessories": "mobile_accessories", "mobile and accessories": "mobile_accessories", "mobile": "mobile_accessories",
        "electronics & appliances": "electronics", "electronics and appliances": "electronics",
        "foot wear": "footwear",
        "cosmetics & beauty": "cosmetics", "cosmetics and beauty": "cosmetics", "beauty": "cosmetics",
        "pharmacy & wellness": "pharmacy", "pharmacy and wellness": "pharmacy",
        "other / mixed business": "other", "other mixed business": "other", "mixed": "other",
    }
    return aliases.get(key)


def infer_category(query: str) -> str | None:
    """Best-effort category inference from a search query (id or None)."""
    text = " ".join(str(query or "").lower().split())
    best: tuple[int, str | None] = (0, None)
    for cid, entry in CATEGORIES.items():
        score = 0
        for hint in entry.get("query_hints", ()):
            if hint and hint in text:
                score += len(hint.split()) + 1
        if score > best[0]:
            best = (score, cid)
    return best[1]


def select_sources(
    category: str | None = None, query: str = ""
) -> tuple[list[str], list[str]]:
    """Return (source_names, warnings) for a discovery request.

    Unknown categories fall back to all sources with a warning. Categories with no
    reliable public source return an empty source list plus an explicit caveat.
    """
    warnings: list[str] = []
    raw = str(category or "").strip()
    cid = normalize_category(raw) if raw else None
    if raw and cid is None:
        warnings.append(
            f"Unknown category {raw!r}; searching all catalogues at low confidence."
        )
    if cid is None and query:
        guessed = infer_category(query)
        if guessed:
            cid = guessed
    if cid is None:
        cid = "other"
    entry = CATEGORIES[cid]
    sources = list(entry["sources"])
    if not sources:
        warnings.append(entry["coverage_caveat"])
    return sources, warnings


def category_for_source(source: str) -> str:
    """Fallback BillFlow category label for a source when tags are uninformative."""
    return {
        SOURCE_FOOD: CATEGORIES["grocery"]["billflow_category"],
        SOURCE_BEAUTY: CATEGORIES["cosmetics"]["billflow_category"],
        SOURCE_PRODUCTS: CATEGORIES["general"]["billflow_category"],
    }.get(source, CATEGORIES["other"]["billflow_category"])


def billflow_similarity(category_label: str) -> str:
    """Resolve a BillFlow category label from a catalogue category string/tag."""
    text = " ".join(str(category_label or "").lower().replace("_", " ").replace(":", " ").split())
    checks = (
        ("instant noodles", "grocery"), ("maggi", "grocery"), ("milk", "grocery"),
        ("beverage", "grocery"), ("snack", "grocery"), ("cereals", "grocery"),
        ("cosmetic", "cosmetics"), ("beauty", "cosmetics"), ("skin care", "cosmetics"),
        ("makeup", "cosmetics"), ("perfume", "cosmetics"), ("hair care", "cosmetics"),
        ("pharmaceutical", "pharmacy"), ("medicine", "pharmacy"), ("vitamin", "pharmacy"),
        ("electronic", "electronics"), ("appliance", "electronics"),
        ("clothing", "clothing"), ("apparel", "clothing"), ("shoe", "footwear"),
        ("mobile", "mobile_accessories"), ("phone", "mobile_accessories"),
    )
    for token, cid in checks:
        if token in text:
            return CATEGORIES[cid]["billflow_category"]
    return ""
