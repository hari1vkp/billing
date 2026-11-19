# BillFlow Barcode Sticker Studio — contract

Standalone product-label printing feature. Must not change POS, invoices,
payments, inventory/stock, pricing, product CRUD or import workflows.

## Backend (`/api/v1/barcode-stickers`, owner-only)
1. `POST /ensure` body `{product_ids: string[]}` →
   `{barcodes: Record<product_id, string>, generated: string[]}`.
   - For each product: if `product.barcode` is non-empty, reuse it EXACTLY.
   - Only when empty: generate a unique internal Code-128 barcode `BF` + 10 digits,
     check tenant-wide uniqueness, save via existing `product_service.update_product`
     (which logs `product.update`), never overwrite an existing barcode, never
     touch stock/price/SKU.
2. `POST /preview` body `{items:[{product_id, quantity}], size, width_mm?, height_mm?, layout}` →
   `{svg: string, total_stickers: number, pages: number, width_mm, height_mm, layout, items:[{product_id, name, barcode, quantity}]}`.
   - SVG shows ONE actual sticker (white bg, thin rounded border, product name small at top, one barcode centered, barcode number below) using the real barcode data.
   - Before rendering, call the same ensure logic so barcodes exist.
3. `POST /pdf` body same as `/preview` → `application/pdf` bytes with a
   `Content-Disposition: inline; filename="billflow-barcode-stickers.pdf"` header.
   - Ensure barcodes first (idempotent).
   - Layout `sheet`: A4 210×297mm, margins 8mm, 3mm gaps, as many small stickers as fit, continue on further pages, never enlarge/crop/overlap.
   - Layout `individual`: page size exactly `width_mm × height_mm`, one sticker per page, using actual dimensions.
   - Sizes: small 40×25 (DEFAULT), medium 50×30, large 60×40, xl 100×50, custom.
   - Each sticker contains ONLY: product name (small top), ONE barcode (center), barcode number below. No SKU/price/manufacturer.
   - Use reportlab: Code128 for arbitrary strings; EAN13 when the stored barcode is a valid 13-digit EAN. Preserve bar proportions/quiet zones, sufficient print resolution.

## Frontend
- New admin page route `/admin/barcode-stickers`, nav item **Barcode Studio**.
- Product browser: paginated/searchable list from existing `GET /products` (name/SKU/barcode search). Each row/card: checkbox, name, SKU, existing barcode, independent quantity input (default 1, min 1). Select all (current page and all filtered results). Live total sticker count.
- Size selector with Small (default 40×25), Medium, Large, Extra Large, Custom (mm inputs). Layout selector A4 sheet / Individual.
- Preview: show backend SVG plus summary (products, quantities, total, dimensions, layout). Buttons: **Generate Preview**, **Print Stickers** (open generated PDF and print / native print in Tauri if available), **Clear Selection**.
- Use existing BillFlow UI primitives/CSS tokens only. Additive CSS. No redesign elsewhere.

## Data / migrations
No new tables or columns. Reuse `products.barcode`. Additive-only if absolutely required.

## Acceptance
Existing barcodes reused, no duplicates, genuine scannable barcodes, correct counts, small default sticker, A4 multi-sticker sheets, individual actual-size printing, no stock changes.
