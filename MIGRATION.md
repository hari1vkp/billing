# BillFlow → Rust desktop migration map

This document records what was inspected in the existing implementation and how
each feature maps to the Rust workspace. The legacy `backend/` and `frontend/`
trees are kept intact until the Rust equivalent is verified.

## Source of truth inspected

- `backend/app/models/` — `Business`, `User`, `Customer`, `CustomerInteraction`,
  `Product`, `Invoice`, `InvoiceItem`, `Payment`, `StockMovement`, `ActivityLog`.
- `backend/app/services/invoice_service.py` — GST/discount calculation engine,
  invoice numbering, status recalculation.
- `backend/app/services/payment_service.py` — cashier confirmation invariant,
  stock decrement guarded by `stock_adjusted`, webhook verification.
- `backend/app/services/analytics_service.py` — all metrics computed from rows.
- `backend/app/services/pdf_service.py` — invoice PDF layout.
- `frontend/src/pages/POS.tsx`, `frontend/src/components/CheckoutModal.tsx`,
  `frontend/src/components/Layout.tsx`, `frontend/src/components/StaffLayout.tsx`,
  `frontend/src/index.css` — UI hierarchy, spacing and the black/white/orange
  identity that the desktop UI must reproduce.

## Feature mapping

| Existing feature | Rust module | Notes |
| --- | --- | --- |
| POS billing, barcode scan, cart | `desktop/src/ui/pos.rs` + `shared/src/services/billing.rs` | Keyboard-wedge scanner; Enter lookup; duplicate scan increments quantity. |
| GST/discount calculation | `shared/src/services/billing.rs::calculate` | Same rounding and formula as `invoice_service.py`. |
| Checkout modal (UPI QR / Cash) | `desktop/src/ui/checkout.rs` | Two tabs only; Complete Sale is the only primary action; Cancel creates nothing. |
| Dynamic UPI QR | `shared/src/services/payments.rs` | `upi://pay` URI with VPA, payee, amount, transaction ref; QR matrix rendered natively. |
| Cash / cashier-confirmed payment | `shared/src/services/billing.rs::checkout` | Payment recorded as manually confirmed — never claims bank verification. |
| Invoice generation + PDF | `shared/src/services/reports.rs` | `printpdf`; exported to app-data exports directory. |
| Inventory + stock movements | `shared/src/services/inventory.rs`, `shared/src/repo.rs` | Owner unrestricted; staff limited reasons and delta ≤ 20. |
| Customers + interactions | `shared/src/repo.rs` | Search, stats, notes. |
| Admin dashboard + analytics | `shared/src/services/analytics.rs`, `desktop/src/ui/admin.rs` | Values read from SQLite, never hardcoded. |
| Roles and permissions | `shared/src/auth.rs` + UI gates | `Owner` / `Staff`; staff cannot see admin screens. |
| Activity audit log | `shared/src/audit.rs` | Invoice, payment, stock, product, customer, staff actions. |
| CSV reports | `shared/src/services/reports.rs::sales_csv` | Date-filtered. |
| Multi-business isolation | every repo query filters by `business_id` | Same rule as backend. |

## Persisted data differences

The web app uses PostgreSQL. The Rust desktop app uses SQLite in the OS
application-data directory. Refresh tokens and webhook events are server-only
concerns and are intentionally not migrated; the desktop app has local
PBKDF2 password accounts and explicit cashier confirmation instead.
