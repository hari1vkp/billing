"""Unauthenticated, customer-facing endpoints.

These are read-only for invoice details and allow a customer to *declare* a
payment. Declared payments stay in `submitted` status until a verified webhook
or an authenticated staff member confirms them.
"""

import base64

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.business import Business
from app.models.customer import Customer
from app.schemas.payment import (
    PublicInvoiceOut,
    PublicPaymentSubmit,
    PaymentOut,
)
from app.services import invoice_service, payment_service, upi_service

router = APIRouter(prefix="/public", tags=["Public Payment Link"])


@router.get("/invoices/{token}", response_model=PublicInvoiceOut)
def public_invoice(token: str, db: Session = Depends(get_db)):
    invoice = invoice_service.get_by_public_token(db, token)
    if not invoice or invoice.status in ("draft", "cancelled"):
        raise HTTPException(status_code=404, detail="Invoice not found")
    business = db.get(Business, invoice.business_id)
    customer = db.get(Customer, invoice.customer_id)

    out = PublicInvoiceOut.model_validate(invoice)
    out.business_name = business.name
    out.business_upi_id = business.upi_id
    out.business_upi_name = business.upi_name or business.name
    out.currency = business.currency
    out.customer_name = customer.name if customer else None
    out.items = [
        {
            "description": i.description,
            "quantity": float(i.quantity),
            "unit_price": float(i.unit_price),
            "line_total": float(i.line_total),
        }
        for i in invoice.items
    ]
    payments = payment_service.get_payments_for_invoice(
        db, invoice.business_id, invoice.id
    )
    out.payments = [
        {
            "id": p.id,
            "method": p.method,
            "status": p.status,
            "amount": float(p.amount),
            "reference": p.reference,
            "created_at": str(p.created_at),
        }
        for p in payments
    ]
    return out


@router.get("/invoices/{token}/qr")
def public_qr(token: str, db: Session = Depends(get_db)):
    invoice = invoice_service.get_by_public_token(db, token)
    if not invoice or invoice.status in ("draft", "cancelled"):
        raise HTTPException(status_code=404, detail="Invoice not found")
    business = db.get(Business, invoice.business_id)
    if not business.upi_id:
        raise HTTPException(status_code=404, detail="UPI not configured for this business")
    uri = upi_service.invoice_upi_uri(business, invoice)
    png = upi_service.generate_qr_png(uri)
    return {
        "upi_uri": uri,
        "qr_data_url": "data:image/png;base64," + base64.b64encode(png).decode(),
        "amount": float(invoice.balance_amount or invoice.total_amount),
        "upi_id": business.upi_id,
        "payee_name": business.upi_name or business.name,
        "currency": business.currency,
        "transaction_ref": invoice.transaction_ref or invoice.invoice_number,
    }


@router.post(
    "/invoices/{token}/payments",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_payment(token: str, data: PublicPaymentSubmit, db: Session = Depends(get_db)):
    try:
        return payment_service.submit_public_payment(db, token, data)
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except payment_service.PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
