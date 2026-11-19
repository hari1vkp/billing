# BillFlow wholesale/retail pricing mode — contract

Single POS workflow. No separate billing module, no duplicate pricing engine.

## Data model (additive, non-destructive migrations)
- `products.wholesale_discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0` (0..100).
- `invoices.pricing_mode VARCHAR(16) NOT NULL DEFAULT 'retail'` (`retail`|`wholesale`).
- `invoice_items.wholesale_discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0` — the
  product discount actually applied to that line at bill time (0 in retail mode).

Wholesale price is always derived, never stored as an independent selling price:
`wholesale_price = round2(retail_price * (1 - wholesale_discount_percent / 100))`.

## Backend (FastAPI / PostgreSQL)
- `ProductCreate`, `ProductUpdate`, `ProductOut` gain `wholesale_discount_percent`
  (0..100 validator). `ProductOut` exposes computed `wholesale_price`.
- `InvoiceCreate` / `InvoiceUpdate` / `InvoiceOut` / `InvoiceListItem` gain
  `pricing_mode` (`retail` default, pattern validated).
- `InvoiceItemOut` gains `wholesale_discount_percent`.
- `invoice_service._build_items(db, business_id, items, pricing_mode)`:
  when an item resolves to a product, compute the authoritative unit price from
  `product.price` and the selected mode (wholesale uses the product's
  `wholesale_discount_percent`). Record `wholesale_discount_percent` on the item.
  A client-supplied `unit_price` is ignored for product-backed lines when it
  disagrees with the mode-derived price (keeps totals authoritative).
  Non-product lines keep the supplied `unit_price`.
- Invoice creation persists `pricing_mode`. Existing items already store the
  actual `unit_price`, so editing products later cannot alter completed bills.
- Migration helper adds the three columns + indexes if missing.
- Existing tax/discount/rounding logic unchanged.

## Frontend (React / TypeScript)
- `Product` / `ProductInput` gain `wholesale_discount_percent`; `Invoice` /
  `InvoiceListItem` / POS checkout payload gain `pricing_mode`.
- POS: compact segmented switch **Retail | Wholesale**, Retail default, visible
  in cart header and checkout. Effective unit price helper uses the product's
  wholesale discount in wholesale mode. Cart line display, totals, and checkout
  all use effective prices. Switching modes recalculates everything; switching
  back restores retail prices. `onSaleComplete` clears the cart (mode returns to
  Retail for the next bill unless the app chooses to keep it — default Retail).
- Product form: add **Wholesale Discount (%)** input (0..100) and a read-only
  calculated wholesale price preview next to retail price. Product table can
  show the derived wholesale price.
- Invoice detail/list shows the bill's pricing mode. No other screen redesign.

## SQLite / Tauri
- Add the same three columns to `shared` models/migrations and keep the existing
  Rust checkout computing the mode-derived unit price so SQLite mode stays
  compatible. No new Rust business module; extend the existing shared engine.

## Acceptance
Retail default; cashier switches during billing; per-product discounts; totals
recalculate both ways; completed invoices keep charged prices; drafts keep mode;
existing retail flows unchanged.
