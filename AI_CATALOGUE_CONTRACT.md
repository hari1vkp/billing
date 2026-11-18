# BillFlow AI-assisted catalogue onboarding — contract

The AI assistant is EXTERNAL. BillFlow only generates a ready-to-copy prompt,
opens official AI websites, downloads the official template, parses the file
the owner brings back, validates it, and imports it into the existing
`products` / `stock_movements` / `activity_logs` tables. No AI account, API key
or automatic generation is claimed.

## Official import template (14 columns, exact order)
```
Product Name,Brand,Category,Subcategory,Variant,Size / Pack Size,Barcode,Barcode Type,SKU,Purchase Price,Selling Price,Discount Type,Discount Value,Opening Stock
```
Internal canonical keys (used in JSON):
`name, brand, category, subcategory, variant, size_pack, barcode, barcode_type, sku, cost_price, selling_price, discount_type, discount_value, quantity`

Legacy files using the previous 7-column template still work via aliases:
`name, barcode, cost_price, selling_price, quantity, category, gst_rate`.
`gst_rate` is optional and defaults from business settings when absent.

## Backend endpoints (all owner-only, `/api/v1`)
- `GET /products/ai/categories` → `{categories:[{id,label,description}]}` covering
  grocery, general store, clothing, mobile accessories, electronics, footwear,
  cosmetics, pharmacy, other.
- `POST /products/ai/prompt` body `{category_id, business_name?, extra_notes?}` →
  `{prompt: string}` with a long, category-tailored prompt instructing the AI
  to produce a comprehensive catalogue (hundreds of relevant Indian-market
  products, brands, sizes, packs, colours, categories/subcategories), using the
  EXACT 14-column header, never inventing barcodes, giving prices only when
  known, and leaving unknown fields blank.
- `GET /products/import/template` → updated CSV with 14-column header, two
  `#`-prefixed instruction rows and two example rows (one manufacturer barcode,
  one internal barcode blank). Attachment `billflow-product-catalogue-template.csv`.
- `GET /products/barcodes/labels?ids=<id1,id2,...>` → PDF label sheet (Code 128)
  using reportlab; one label per product with product name, SKU, barcode and
  internal/manufacturer marker. `Content-Type: application/pdf`.
- `POST /products/import/parse` and `/products/import/commit` keep their paths
  and response envelope but rows gain the new fields above.

## Barcode rules
- Manufacturer barcode present → preserve exactly, `barcode_type='manufacturer'`.
- No barcode → backend generates a unique internal Code-128-compatible barcode
  `BF` + 10 digits and `barcode_type='internal'`; generate a SKU if missing.
- Validate uniqueness within the file and against the tenant DB; invalid/duplicate
  rows are reported, never silently overwritten.
- Generated barcodes must be scannable by the existing POS barcode lookup.
- Clothing size/colour variants are separate product rows, each with its own
  unique SKU/barcode; name is decorated as `Base — Variant / Size`.

## Prices / discounts
- Purchase price, selling price, discount type (`none|percent|flat`), discount
  value and opening stock are editable in the preview.
- Blank/unknown prices remain blank; selling price is required for import.
- Discount value must be >= 0 and <= 100 when type is `percent`.
- Product model gains `discount_type: String(16) default 'none'` and
  `discount_value: Numeric(14,2) default 0`; additive DB migration required.

## Frontend
- New guided wizard `src/pages/AICatalogue.tsx` with steps 1–7: category select,
  generate prompt, readable textarea, Copy / Open ChatGPT / Open Gemini /
  Download template, plain-language instructions, file upload, editable preview,
  import summary. Reuses existing UI primitives and CSS tokens only.
- Entry points: Admin → Inventory header button **Create Products with AI**, and
  Settings/business onboarding card/button. No redesign of other screens.
- Extend `ImportProducts.tsx` preview to show and edit the new fields.
- Inventory toolbar: **Print barcode labels** button using `downloadFile`.

## Rust / SQLite compatibility
- Rust must NOT duplicate AI/prompt/import business logic. Only add the two new
  product columns (`discount_type`, `discount_value`) to the shared SQLite model
  and migration so desktop SQLite stays compatible. Native print/download uses
  existing Tauri commands.
