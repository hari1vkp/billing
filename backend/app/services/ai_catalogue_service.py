"""Deterministic prompt templating for the external AI catalogue assistant.

This module never calls an AI service or network endpoint. It only builds a
ready-to-copy prompt that the business owner can paste into ChatGPT, Gemini or
any other external assistant. The assistant is responsible for the actual
catalogue; BillFlow only parses and validates the file the owner brings back.
"""

from __future__ import annotations

# The exact 14-column header from AI_CATALOGUE_CONTRACT.md. Kept here as the
# single source of truth so the prompt and the downloadable template can never
# drift apart.
CATALOGUE_HEADER = (
    "Product Name,Brand,Category,Subcategory,Variant,Size / Pack Size,Barcode,"
    "Barcode Type,SKU,Purchase Price,Selling Price,Discount Type,Discount Value,"
    "Opening Stock"
)

# Extra guidance that is shown in the API response and used to tailor prompts.
_CATEGORY_DETAILS: dict[str, dict] = {
    "grocery": {
        "label": "Grocery & Staples",
        "description": "Kirana stores, supermarkets and grocery shops selling staples, snacks, beverages and daily-use goods.",
        "areas": [
            "staples such as att flour, rice, pulses, dal, sugar, salt and besan",
            "snacks and biscuits (namkeen, chips, cookies, cakes and packaged snacks)",
            "beverages (tea, coffee, juices, soft drinks, energy drinks and bottled water)",
            "edible oils, ghee, spices, masalas and condiments",
            "dairy products such as milk, curd, cheese, butter and paneer",
            "packaged foods (breakfast cereals, noodles, pasta, jams and ready-to-eat meals)",
            "personal care (soap, shampoo, toothpaste, talcum powder and hand wash)",
            "home cleaning (detergent, dishwash, floor cleaner, phenyl and tissues)",
        ],
        "brands": "Amul, Parle, Britannia, Aashirvaad, Fortune, Saffola, Tata, Maggi, Nestle, Dabur, Himalaya, Colgate, HUL and generic/store-brand items",
    },
    "general": {
        "label": "General Store",
        "description": "General stores and neighbourhood shops selling a broad mix of household, stationery and everyday merchandise.",
        "areas": [
            "stationery (notebooks, pens, pencils, erasers, files and calculators)",
            "kitchen and home utensils (plasticware, steel containers, cookware and storage boxes)",
            "cleaning and laundry supplies",
            "toys, games and small household accessories",
            "batteries, torches, lights and small hardware items",
            "personal care and basic cosmetics",
            "packaged snacks, drinks and groceries commonly kept at a general store",
            "seasonal and utility items such as umbrellas, bags and hygiene products",
        ],
        "brands": "HUL, P&G, ITC, Classmate, Camlin, Reynolds, Cello, Borosil, Eveready, Philips and local generic brands",
    },
    "clothing": {
        "label": "Clothing & Apparel",
        "description": "Retailers selling men's, women's and children's garments with multiple sizes, colours and style variants.",
        "areas": [
            "men's garments (t-shirts, shirts, trousers, jeans, jackets and innerwear)",
            "women's garments (kurtis, sarees, tops, leggings, dresses and dupattas)",
            "children's clothing for different age groups",
            "ethnic and occasion wear, plus everyday basics",
            "sizes S, M, L, XL, XXL and kids' age bands, where relevant",
            "colours and fabric variants such as cotton, linen, denim and polyester",
            "seasonal collections and accessories such as scarves and caps",
            "each distinct size/colour/fabric combination as its own catalogue row",
        ],
        "brands": "Peter England, Allen Solly, Van Heusen, Biba, FabIndia, Roadster, Levi's, Wildcraft, Monte Carlo and generic/unbranded garments",
    },
    "mobile": {
        "label": "Mobile & Accessories",
        "description": "Shops selling mobile phones, cases, chargers, cables, audio devices and related accessories.",
        "areas": [
            "back cases and covers for popular phone models",
            "screen protectors and tempered glass",
            "chargers, adapters and USB/Type-C cables",
            "power banks and batteries",
            "wired and Bluetooth earphones, headphones and speakers",
            "smartwatches, fitness bands and phone holders",
            "memory cards, car chargers and other common accessories",
            "model-specific variants listed as separate rows",
        ],
        "brands": "boAt, Noise, Mi, Samsung, Apple, OnePlus, Realme, Ubon, Portronics and compatible generic accessories",
    },
    "electronics": {
        "label": "Electronics & Appliances",
        "description": "Dealers selling consumer electronics, home appliances and electrical goods.",
        "areas": [
            "kitchen appliances (mixers, grinders, microwave ovens, kettles and induction cooktops)",
            "home appliances (fans, air coolers, air conditioners, refrigerators and washing machines)",
            "lighting including LED bulbs, tube lights and lamps",
            "audio and video products such as televisions and soundbars",
            "small personal-care appliances",
            "electrical accessories, extension boards and switches",
            "capacity, model and colour variants as separate rows",
            "energy-efficient and locally serviced product options",
        ],
        "brands": "Voltas, Godrej, Philips, Samsung, LG, Havells, Prestige, Bajaj, Mi, Crompton and reliable generic alternatives",
    },
    "footwear": {
        "label": "Footwear",
        "description": "Retailers selling shoes, sandals, slippers and footwear accessories across sizes and colours.",
        "areas": [
            "men's shoes (formal, casual, sports and loafers)",
            "women's footwear (sandals, heels, flats and casual shoes)",
            "children's shoes and school footwear",
            "slippers, flip-flops and daily-wear footwear",
            "sports and running shoes",
            "size ranges for adults and children plus colour variants",
            "socks, insoles and basic footwear accessories",
            "each size/colour combination as a separate catalogue row",
        ],
        "brands": "Bata, Liberty, Sparx, Puma, Adidas, Nike, Crocs, Lakhani, Khadims and generic footwear",
    },
    "cosmetics": {
        "label": "Cosmetics & Beauty",
        "description": "Shops selling skin care, hair care, makeup, fragrances and beauty accessories.",
        "areas": [
            "skin care (cleansers, moisturisers, sunscreens, serums and face washes)",
            "hair care (shampoo, conditioner, hair oil, hair colour and styling products)",
            "makeup (lipsticks, foundations, compacts, eyeliners, mascaras and palettes)",
            "fragrances and deodorants",
            "nail care and beauty tools",
            "men's grooming products",
            "size and shade variants as separate rows",
            "both premium and affordable Indian beauty brands",
        ],
        "brands": "Lakme, Maybelline, L'Oreal, Colorbar, Mamaearth, Minimalist, Himalaya, Dabur, PLUM, Sugar and generic products",
    },
    "pharmacy": {
        "label": "Pharmacy & Wellness",
        "description": "Chemists and pharmacies selling over-the-counter medicines, wellness products and first-aid supplies.",
        "areas": [
            "common over-the-counter and household remedies",
            "vitamins, supplements and nutrition products",
            "first-aid supplies, bandages and antiseptics",
            "personal care and hygiene products",
            "baby care and basic wellness items",
            "Ayurvedic and homeopathic wellness products",
            "pack sizes and strengths where commonly sold over the counter",
            "do not invent prescription medicines, dosages or medical claims",
        ],
        "brands": "Dabur, Himalaya, Charak, Zincovit, Volini, Crocin, Dolo, Pampers and generic wellness items",
    },
    "other": {
        "label": "Other / Mixed Business",
        "description": "A mixed retail business that does not fit neatly into one of the categories above.",
        "areas": [
            "the main product lines this business actually sells",
            "fast-moving everyday items and impulse purchases",
            "different pack sizes and price points",
            "colour, model, size or flavour variants as separate rows",
            "well-known Indian brands in the relevant lines",
            "generic and unbranded equivalents",
            "seasonal products the shop commonly stocks",
            "logical categories and subcategories that make the catalogue easy to browse",
        ],
        "brands": "well-known Indian brands for the relevant product lines together with generic alternatives",
    },
}

CATEGORIES = [
    {
        "id": category_id,
        "label": details["label"],
        "description": details["description"],
    }
    for category_id, details in _CATEGORY_DETAILS.items()
]


def _category(category_id: str | None) -> tuple[str, dict]:
    key = str(category_id or "").strip().lower()
    if key not in _CATEGORY_DETAILS:
        key = "other"
    return key, _CATEGORY_DETAILS[key]


def generate_prompt(
    category_id: str,
    business_name: str | None = None,
    extra_notes: str | None = None,
) -> str:
    """Return a long, category-tailored prompt for an external AI assistant."""
    key, details = _category(category_id)
    business = str(business_name or "").strip() or "this Indian business"
    focus = "\n".join(f"  - {area}." for area in details["areas"])

    parts = [
        f"You are a meticulous product-catalogue assistant for an Indian retail business. "
        f"The business is {business}, and its main line is {details['label'].lower()}.",
        "",
        "YOUR TASK",
        "Generate a comprehensive, ready-to-import product catalogue for this business. "
        "Produce at least 150-300 relevant products, not a short sample. Cover the full "
        "breadth of a real Indian store rather than a handful of example rows. Every row "
        "must represent a realistic product that such a business could actually sell.",
        "",
        f"CATEGORY FOCUS — {details['label']}",
        f"{details['description']}",
        "Make sure the catalogue covers all of these areas:",
        focus,
        "",
        "BRANDS AND GENERIC ITEMS",
        f"Include a healthy mix of recognisable Indian brands AND generic/unbranded items. "
        f"Use brands such as {details['brands']}. Add plain generic descriptions for "
        "unbranded products too, so the catalogue is useful for a real shop.",
        "",
        "ORGANISATION AND VARIANTS",
        "Organise the catalogue into sensible categories and subcategories (for example, "
        "Beverages > Tea or Clothing > Men > T-Shirts). Put the category and subcategory "
        "in their own columns on every row. Create a separate row for each meaningful "
        "variant: size, pack size, colour, shade, flavour or model. For clothing and "
        "footwear in particular, list the available sizes and colours as individual rows "
        "and describe them in the Variant and Size / Pack Size columns.",
        "",
        "BARCODES — DO NOT INVENT OFFICIAL BARCODES",
        "Never invent, guess or fabricate an official GS1/EAN/UPC barcode. Leave the "
        "Barcode cell completely blank for every product unless you are certain of a "
        "genuine barcode printed on the real product. BillFlow generates its own unique "
        "internal Code-128-compatible barcode and SKU for blank rows. When you do know a "
        "real barcode, put it in Barcode and write 'manufacturer' in Barcode Type; for "
        "blank barcodes write 'internal' in Barcode Type. Never repeat a barcode across "
        "two rows.",
        "",
        "PRICES, DISCOUNTS AND STOCK — DO NOT GUESS",
        "Give a price only when you know it or it is a reliable, typical Indian-market "
        "price; leave the cell blank when it is unknown. Never make up a precise price "
        "and present it as a fact. Purchase Price and Selling Price are in Indian Rupees. "
        "Discount Type must be one of none, percent or flat; Discount Value must be blank "
        "or 0 for 'none', a number from 0 to 100 for 'percent', and a rupee amount for "
        "'flat'. Opening Stock may be left blank and set later in the BillFlow preview.",
        "",
        "OUTPUT FORMAT — CSV OR EXCEL ONLY",
        "Return a CSV file or an Excel spreadsheet and nothing else: no commentary, no "
        "markdown, no introduction, no footnotes, no JSON. The first row must be this "
        "EXACT 14-column header, in this exact order, with these exact spellings:",
        CATALOGUE_HEADER,
        "Then write one product per row. Use exactly these columns in every row: Product "
        "Name, Brand, Category, Subcategory, Variant, Size / Pack Size, Barcode, Barcode "
        "Type, SKU, Purchase Price, Selling Price, Discount Type, Discount Value, Opening "
        "Stock. Leave any unknown cell empty — never fill it with guesses, dashes, 'N/A' "
        "or placeholder text. Make sure commas inside a value are quoted correctly.",
        "",
        "QUALITY CHECK BEFORE YOU FINISH",
        "Review your output and confirm it has at least 150-300 product rows, uses the "
        "exact header above, has no invented barcodes, has no repeating barcodes, and "
        "leaves all uncertain values blank. Return the finished CSV or Excel file only.",
    ]

    note = str(extra_notes or "").strip()
    if note:
        parts.extend(
            [
                "",
                "ADDITIONAL NOTES FROM THE BUSINESS OWNER",
                "Also take these instructions into account when building the catalogue:",
                note,
            ]
        )

    return "\n".join(parts)
