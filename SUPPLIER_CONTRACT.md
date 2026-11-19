# BillFlow supplier management — contract

General-purpose across all business types. No hardcoded industry categories,
brands or product types. All new records are tenant-scoped by `business_id`.

## Models (additive tables + migrations)
- `suppliers`: id, business_id, name (supplier/company name, required),
  contact_person, phone, whatsapp, email, address, category (free text),
  brands (free text / comma list), notes, is_active, timestamps.
- `supplier_products`: id, business_id, supplier_id, product_id (nullable FK to
  existing products), custom_name (used when no BillFlow product), supplier_sku,
  supplier_price (Numeric), notes. A supplier may link many products; many
  suppliers may link the same product. NEVER create inventory products here.
- `purchase_reminder_lists`: id, business_id, supplier_id, title, status
  (`pending`|`converted`), notes, created_by, timestamps.
- `purchase_reminder_items`: id, list_id, product_id (nullable), name (required),
  quantity (Numeric), unit (free text: pcs/boxes/metres/kg...), expected_price
  (Numeric nullable), notes, is_purchased bool, timestamps.
- `supplier_visits`: id, business_id, supplier_id, visit_date, discussion_notes,
  items_discussed, items_requested, follow_up, next_visit_date, notes,
  created_by, timestamps.
- `supplier_purchases`: id, business_id, supplier_id, purchase_number,
  purchase_date, reminder_list_id (nullable), notes, created_by, timestamps.
- `supplier_purchase_items`: id, purchase_id, product_id, quantity, unit_price,
  line_total, reminder_item_id (nullable).

`StockMovement.reason` gains `purchase`; conversion creates real movements via
the EXISTING `inventory_service.record_movement` with
`reference = purchase_number`. Marking a reminder item purchased changes ONLY
`is_purchased` — no stock mutation.

## API (all under `/api/v1/suppliers`, owner-only)
- `GET /suppliers` — search `q`, filter `category`, `product_type`, pagination,
  sorting. Returns supplier with product count and phone/whatsapp.
- `GET /suppliers/categories` — distinct categories/brands derived from existing
  supplier rows (user-defined, never seeded industry lists).
- `POST /suppliers`, `PATCH /suppliers/{id}`, `GET /suppliers/{id}` (includes
  products, reminder lists, visits), `DELETE /suppliers/{id}` (deactivate).
- `GET/POST/PATCH/DELETE /suppliers/{id}/products` — supplier-product links.
  Product association must reference an existing BillFlow product OR a custom
  name; never insert into `products`.
- `GET/POST/PATCH/DELETE /suppliers/reminders/{list_id}/items` — reminder items.
- `POST /suppliers/{id}/reminders` — create a list; `GET /suppliers/{id}/reminders`.
- `POST /suppliers/reminders/{list_id}/convert-to-purchase` body
  `{purchase_date?, notes?, only_purchased?: bool = true}` → creates a
  `supplier_purchase` plus stock movements for linked BillFlow products only,
  marks the list `converted`. Custom-name items without a product_id are carried
  into notes, not into inventory. Transaction-safe.
- `GET/POST /suppliers/{id}/visits` — visit history.

## Frontend
- New admin nav item **Suppliers** and route `/admin/suppliers`. No other page
  redesign. Supplier dashboard with search/filter/sort, add/edit modal, and a
  profile drawer/page with tabs **Products**, **Purchase Reminders**, **Visits**.
- User-defined categories/brands via free-text inputs with suggestions from
  `/suppliers/categories` (datalist-style), never hardcoded industry lists.
- Reminder lists: multiple per supplier; items support existing product picker
  or custom name, quantity, free-text unit, expected price, notes, purchased
  checkbox; pending items remain visible for next visit; convert button calls
  the API.
- Visits: quick form + history table.
- Existing BillFlow UI primitives/CSS only; responsive.

## SQLite / Tauri
Add the same additive tables/columns to the shared SQLite schema and migration.
No supplier business logic in Rust; native dialogs/printing only if needed.

## Acceptance
No industry-specific hardcoding; configurable categories/groups; multiple
brands/products per supplier; reminders and visits; pending carry-forward;
conversion uses existing inventory receiving; no stock change on reminder tick.
