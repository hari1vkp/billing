# Supplier-specific product selection & purchase reminder — contract

Enhancement of the existing Supplier module only. No POS or general inventory
changes beyond additive product `unit` metadata.

## Backend changes
1. Add `products.unit: VARCHAR(32) NOT NULL DEFAULT 'pcs'` (free text, owner
   editable) and optional `supplier_products.unit` override (same type). Add
   additive idempotent PostgreSQL migration. Include `unit` in product schemas
   and supplier-product schemas.
2. Enrich `GET /api/v1/suppliers/{supplier_id}/products` response with display
   metadata for cards, using ONLY the existing supplier-product relationship:
   `product_name`, `product_brand`, `product_category`, `product_variant`,
   `product_size_pack`, `product_unit`, `unit` (supplier override, falling back
   to product unit). Derive brand/category/variant/size from the existing
   product description metadata when explicitly stored there; never invent.
   Never return products that are not linked to this supplier.
3. Server-side relationship validation: when creating/updating a reminder item
   with `product_id`, require an existing `SupplierProduct` link between that
   item's reminder list supplier and the product (404/422 otherwise). A product
   may be linked to multiple suppliers.
4. `POST /api/v1/suppliers/{supplier_id}/reminders/quick-save` body:
   `{title: string, notes?: string, items: [{product_id: string, quantity: float > 0, unit?: string, expected_price?: float|null, notes?: string}]}`
   → creates the reminder list and all items in ONE transaction, defaults each
   item's `unit` from the supplier-product/product unit, and returns the list
   with items. Duplicate `product_id` in the payload keeps the first quantity.
5. Duplicate prevention on `POST /suppliers/reminders/{list_id}/items`: if an
   item for the same `product_id` already exists in that list, return the
   existing item unchanged (status 200) instead of inserting a duplicate.
6. Patch reminder item validation: `quantity` must be > 0 when supplied.
7. `DELETE /api/v1/suppliers/reminders/{list_id}` → delete a reminder and its
   items (no stock change).
8. `POST /api/v1/suppliers/reminders/{list_id}/carry-forward` → create a NEW
   pending list with the same title + " (next visit)" and copy only
   `is_purchased == false` items with their quantities/units/notes.
9. Existing `convert-to-purchase` stays unchanged: saving/ticking reminders
   NEVER changes stock; only conversion creates purchase stock movements.

## Frontend (existing Suppliers.tsx only)
- Replace the current reminder-item form with a two-column selection area:
  LEFT = supplier-linked product cards from `GET /suppliers/{id}/products`
  ONLY (never `/products` catalogue for selection), showing name, brand/category,
  variant/size, unit, and a clear Selected indicator. Click toggles selection.
  RIGHT = selected products with inline editable quantity and unit (text) fields,
  remove button, and a single **Save Reminder** action calling `quick-save`.
- Show the supplier name at the top of the section. If no supplier products,
  show exactly "No products linked to this supplier yet." plus a button that
  switches to the Products tab to associate products.
- Saved reminders remain listable/editable: open a list to edit quantities,
  add/remove products, tick purchased, carry forward unfinished items, delete,
  and convert to purchase. Reopening must preserve quantities and statuses.
- When switching suppliers, clear selection/loaded products so no products from
  another supplier can leak into the new reminder. Validate locally that card
  product ids belong to the current supplier's linked products.
- Reuse existing UI primitives/CSS tokens; compact cards, responsive grid.

## SQLite
Add `unit` columns to shared Product/SupplierProduct models and migration only;
no supplier business logic in Rust.

## Acceptance
Only supplier-linked products shown; click-to-select/deselect; inline qty+unit;
no duplicates; save/reopen/edit/delete/carry-forward; no stock change except
existing purchase conversion.
