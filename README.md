# BillFlow — Smart Billing, CRM & Business Analytics

A full-stack billing and business-management platform built for small and medium businesses in India. Manage customers, create GST-aware invoices, collect payments through dynamic UPI QR codes, track inventory, and understand business performance from analytics computed entirely from real database records.

---

## Features

- **Billing & invoices** — multi-item invoices with quantity, unit price, line discounts, GST and invoice-level discount; automatic subtotal/tax/total calculation; PDF invoices with business details and an embedded UPI QR; full history and statuses (`draft`, `unpaid`, `partially_paid`, `paid`, `cancelled`).
- **UPI payments** — a unique, amount-locked `upi://pay` QR for every invoice, generated from the business's registered VPA and name. Customers scan with any UPI app and submit a UTR reference through the public payment link.
- **Payment confirmation you can trust** — a customer submitting a payment **never** marks it paid. Only an authenticated staff confirmation with a UTR, or an HMAC-SHA256-signature-verified provider webhook, can confirm a payment. Webhooks are idempotent; confirmed payments are recorded and stock is adjusted exactly once.
- **Mini CRM** — customer profiles, billing/payment history, totals and outstanding balances, last transaction, notes and interaction history, search and filters, frequent/inactive customer signals.
- **Analytics dashboard** — today's sales/transactions/collections, weekly/monthly/yearly revenue, month-over-month growth, best-selling products, most valuable customers, pending payments, payment-method breakdown, 12-month sales trends, date-range filters and downloadable CSV reports. Every figure is computed from persisted records.
- **Products & inventory** — products and services, SKU/HSN, price, GST rate, stock, automatic stock decrement after confirmed sales, low-stock alerts, service items without inventory.
- **Multi-tenant architecture** — every record is scoped to a `business_id`. JWT access tokens + rotating, hashed refresh tokens with reuse detection, bcrypt password hashing, role-based access (`owner`/`staff`), Pydantic validation, layered models/schemas/repositories/services/routers.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Recharts, Lucide icons, React Router |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Database | PostgreSQL 16 |
| Auth | JWT (PyJWT), bcrypt, rotating refresh tokens stored as SHA-256 hashes |
| PDF | ReportLab |
| QR | `qrcode` (NPCI UPI deep-link URI) |

---

## Quick start (local development)

### 1. Database

PostgreSQL is already running in a Docker container for this workspace:

```bash
docker run -d --name billing-db \
  -e POSTGRES_USER=billing \
  -e POSTGRES_PASSWORD=billing_dev_pass \
  -e POSTGRES_DB=billing \
  -p 5433:5432 postgres:16-alpine
```

Connection string (also in `backend/.env`):

```
postgresql+psycopg2://billing:billing_dev_pass@localhost:5433/billing
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py                 # optional demo data (creates schema + sample records)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Tables are created automatically at startup via `Base.metadata.create_all`. The seed script loads a demo business, users, customers, products, invoices and payments.

**Demo login:** `demo@billingapp.com` / `Demo@1234` (staff: `staff@billingapp.com` / `Staff@1234`)

Interactive API docs: <http://localhost:8000/docs>

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to `http://localhost:8000`.

### 4. Full stack with Docker Compose (optional)

```bash
# Stop the local billing-db container first so port 5433 is free
docker stop billing-db && docker rm billing-db
docker compose up --build
```

This starts PostgreSQL, the FastAPI backend and the Vite frontend together.

---

## Project structure

```
backend/
  app/
    core/          config, database/session lifecycle, security, auth dependencies
    models/        SQLAlchemy ORM models (tenant-scoped)
    schemas/       Pydantic request/response validation
    repositories/  data access queries
    services/      business logic (calculations, payments, analytics, PDF, UPI)
    api/           FastAPI routers
    main.py        app, CORS, exception handlers, schema creation
  seed.py
frontend/
  src/
    api/           typed fetch client with refresh-token rotation
    context/       authentication state
    components/    layout and reusable UI primitives
    pages/         dashboard, billing, customers, products, payments, analytics, settings, public payment
```

---

## Payment workflow

1. Staff creates an invoice; the exact payable amount is embedded in a per-invoice UPI URI and QR code.
2. Customer scans the QR and pays from any UPI app, then opens the public payment link (`/pay/<token>`) and submits their UTR. The payment is recorded as **`submitted`** — the invoice is still unpaid.
3. Either:
   - Staff opens **Payments**, finds the pending payment and clicks **Confirm** after entering the UTR (authenticated action), or
   - A payment provider sends a signed webhook to `POST /api/v1/webhooks/payments/{provider}` with header `X-Webhook-Signature: sha256=<hex HMAC of raw body using PAYMENT_WEBHOOK_SECRET>`.
4. Confirmation updates `paid_amount`, recalculates invoice status and decrements stock once.

Webhook payload example:

```json
{
  "event_id": "evt_abc123",
  "event": "payment.success",
  "data": {
    "status": "success",
    "reference": "UTR123456789012",
    "amount": 1454.88,
    "invoice_number": "SGT-2026-00025"
  }
}
```

---

## Security notes

- Change `SECRET_KEY` and `PAYMENT_WEBHOOK_SECRET` in `backend/.env` before any real deployment.
- Refresh tokens are rotated on every refresh; replaying a used token revokes all sessions for that user.
- All business data is filtered by the authenticated user's `business_id`; cross-tenant IDs return 404.
- Replace the development Postgres password with a strong one for production.
- Webhook signatures are verified over the **raw request body** with constant-time comparison before any state change.

---

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | Sign in |
| POST | `/api/v1/auth/refresh` | Rotate tokens |
| GET | `/api/v1/business` | Business + UPI settings |
| POST/GET/PATCH | `/api/v1/customers` | CRM |
| POST/GET/PATCH | `/api/v1/products` | Products & inventory |
| POST/GET/PATCH | `/api/v1/invoices` | Billing |
| GET | `/api/v1/invoices/{id}/pdf` | PDF invoice |
| GET | `/api/v1/invoices/{id}/qr` | Dynamic UPI QR |
| POST | `/api/v1/payments/{id}/confirm` | Staff confirmation |
| POST | `/api/v1/webhooks/payments/{provider}` | Verified provider webhook |
| GET | `/api/v1/analytics` | Analytics with date filters |
| GET | `/api/v1/analytics/reports/sales.csv` | CSV export |
| GET | `/api/v1/public/invoices/{token}` | Customer payment link data |

Full OpenAPI documentation is served at `/docs`.
