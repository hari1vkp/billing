# BillFlow product onboarding — API contract

All endpoints are under `/api/v1`, require authentication, and are **owner-only**
(`require_owner`). They reuse the existing `Product`, stock-movement and
activity-log records — no parallel product system.

## Backend endpoints (FastAPI / PostgreSQL mode)

### `GET /products/import/template`
CSV download. Header row exactly:
`name,barcode,cost_price,selling_price,quantity,category,gst_rate`
Second row is a commented example beginning with `#` (parser ignores rows whose
name starts with `#`). `Content-Type: text/csv`, attachment filename
`billflow-product-import-template.csv`.

### `POST /products/import/parse` (multipart `file`)
Accepts `.csv`, `.xlsx`, `.xls`. Returns:
```ts
{
  recognized_columns: Record<string, string | null>, // canonical -> actual header
  unsupported_columns: string[],
  total_rows: number,
  error_count: number,
  rows: Array<{
    row_number: number;
    name: string; barcode: string | null;
    cost_price: number | null; selling_price: number | null;
    quantity: number; category: string | null; gst_rate: number;
    errors: string[]; warnings: string[]; valid: boolean;
  }>
}
```
Column aliases to recognise (case/space/punctuation insensitive):
- name: `name`, `product`, `product name`, `item`, `item name`, `description`
- barcode: `barcode`, `bar code`, `ean`, `upc`, `isbn`
- cost_price: `cost`, `cost price`, `purchase price`, `buying price`, `mrp cost`
- selling_price: `price`, `selling price`, `sale price`, `retail price`, `rate`, `mrp`
- quantity: `quantity`, `qty`, `stock`, `opening stock`, `opening qty`, `closing stock`
- category: `category`, `group`, `product group`, `brand`
- gst_rate: `gst`, `gst %`, `tax`, `tax rate`

Validation: name required, selling_price required and >= 0, quantity >= 0
(default 0), gst_rate 0..100 (default from business settings), duplicate
barcodes within the file flagged on later rows, existing barcode in DB flagged
as a warning with the existing product id/name. Never invent missing values.

### `POST /products/import/commit`
```ts
{
  rows: Array<{ name; barcode?; cost_price?; selling_price; quantity; category?; gst_rate? }>,
  overwrite_stock: boolean = false,   // default false
  default_gst_rate?: number
}
```
Returns:
```ts
{ created: number; updated: number; skipped: number;
  errors: Array<{ row: number; message: string }>;
  stock_movements: number; activity_entries: number }
```
Behaviour:
- One DB transaction for the whole batch. Invalid rows are skipped with errors;
  any DB failure rolls back the whole batch.
- New product: `ProductCreate` with opening `stock = quantity`, `track_inventory=true`,
  `is_service=false`, `sku` from barcode when present, `description` from category
  when present, `gst_rate` given/default. Record stock movement reason
  `opening_stock` with quantity_before 0 and quantity_after = quantity.
- Existing product matched by barcode (or exact name+barcode when barcode missing):
  do **not** change price or stock unless `overwrite_stock` is true; when true,
  set stock to the imported quantity and record a `correction` movement.
  Never silently overwrite existing stock.
- Log `product.create` / `product.update` activity per changed row and one
  `product.import` activity with counts.

### `GET /products/barcode/lookup/{barcode}` (owner only)
External catalogue lookup (Open Food Facts v2 public API, no credentials).
Returns:
```ts
{ found: boolean; source: string; barcode: string;
  name?: string; brand?: string; category?: string; image_url?: string;
  price: null; message: string }
```
`price` is ALWAYS null — the API does not provide reliable pricing. If the
service is unreachable return `{found:false, source:"none", ..., message}`
with HTTP 200, never fabricated data. Timeout <= 8s.

### `POST /products/import/ocr` (multipart `file`)
Accepts images (`png,jpg,jpeg,webp`) and PDFs. Uses `pdftotext` for PDFs and
Tesseract for images when available. Returns:
```ts
{ rows: Array<{ name: string; quantity: number | null;
  confidence: number; uncertain_fields: string[]; raw_line: string }>;
  source: string; warnings: string[] }
```
Never guess names/quantities that are not legible; mark them with low
confidence and include the field name in `uncertain_fields`. If OCR is not
installed, return HTTP 503 `{detail:"OCR is not available on this server. Use CSV import or manual entry."}`.

## Frontend (React, existing UI only)
- Add an **Import Products** button to the admin Inventory page header using
  existing `Button`/`Modal`/`Card` primitives. No other screen changes.
- Modal tabs: `Bulk file`, `Barcode`, `Photo / PDF`, `Manual`.
- Bulk: template download via existing `downloadFile('/products/import/template', ...)`,
  file input, parse, editable preview table with valid/invalid badges, error
  messages inline, remove/edit rows, optional "Overwrite existing stock"
  checkbox (default off), commit button, progress + summary.
- Barcode: keyboard-wedge input with Enter, local lookup then catalogue lookup,
  quick-create form requiring name + selling price + opening stock. Camera
  scanning only when `BarcodeDetector`/`getUserMedia` exist; otherwise show a
  short note, never a broken control.
- OCR: file upload, editable preview, uncertain fields visibly marked, require
  explicit confirm before commit.
- Manual: name, selling price, opening stock (default 0), barcode, cost price,
  category — use existing `POST /products`.
- Reuse existing CSS classes/design tokens; do not redesign other screens.

## SQLite / Tauri mode
- `shared/src/services/imports.rs` exposes `import_rows(conn, business_id, user_id, rows, overwrite_stock) -> ImportSummary`
  with the same validation/transaction/opening-stock rules, writing real
  `stock_movements` and `activity_logs`.
- A Tauri command `import_products_csv(csv: String, overwrite_stock: bool)` parses
  a CSV string and calls it. Frontend falls back to this only when the FastAPI
  backend is unavailable; the primary path stays the HTTP API above.
