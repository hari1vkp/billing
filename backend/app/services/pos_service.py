"""Simplified cashier checkout service.

The QR shown in the checkout screen and the invoice finally stored in
PostgreSQL are produced from the same cart and the same transaction reference,
so the amount the customer scans is exactly the amount that gets recorded.

No payment is treated as independently verified: the cashier's "Complete Sale"
action creates a confirmed payment record with an explicit manual-confirmation
note. Never claim a bank/UPI verification happened here.
"""

import base64
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.customer import Customer
from app.schemas.invoice import InvoiceCreate, InvoiceOut
from app.schemas.payment import PaymentCreate, PaymentOut
from app.schemas.pos import (
    PosCheckoutRequest,
    PosCheckoutResponse,
    PosQRResponse,
    PosQuoteRequest,
    Receipt,
)
from app.repositories.invoice_repo import InvoiceRepository
from app.services import audit_service, invoice_service, payment_service, upi_service


class ValidationError(Exception):
    pass


def _transaction_ref(data: PosQuoteRequest) -> str:
    supplied = (data.transaction_ref or "").strip()
    return supplied or f"POS-{uuid.uuid4().hex[:10].upper()}"


def preview_invoice_number(db: Session, business_id: str) -> str:
    """Peek at the invoice number a completed checkout would receive."""
    business = db.get(Business, business_id)
    if not business:
        raise ValidationError("Business not found")
    return InvoiceRepository(db).peek_number(business_id, business.invoice_prefix)


def build_qr(db: Session, business_id: str, data: PosQuoteRequest) -> PosQRResponse:
    business = db.get(Business, business_id)
    if not business or not business.upi_id:
        raise ValidationError("UPI ID is not configured in business settings")

    quote = invoice_service.calculate_quote(
        db, business_id, data.items, data.discount_percent
    )
    ref = _transaction_ref(data)
    payee_name = business.upi_name or business.name
    uri = upi_service.build_upi_uri(
        vpa=business.upi_id,
        payee_name=payee_name,
        amount=quote["total_amount"],
        note=f"Payment for {ref}",
        transaction_ref=ref,
        currency=business.currency,
    )
    png = upi_service.generate_qr_png(uri)
    return PosQRResponse(
        qr_data_url="data:image/png;base64," + base64.b64encode(png).decode(),
        upi_uri=uri,
        amount=quote["total_amount"],
        upi_id=business.upi_id,
        upi_name=payee_name,
        business_name=business.name,
        transaction_ref=ref,
        currency=business.currency or "INR",
        quote=quote,
    )


def complete_checkout(
    db: Session, business_id: str, user_id: str, data: PosCheckoutRequest
) -> PosCheckoutResponse:
    business = db.get(Business, business_id)
    if not business:
        raise ValidationError("Business not found")

    ref = _transaction_ref(data)
    invoice = invoice_service.create_invoice(
        db,
        business_id,
        user_id,
        InvoiceCreate(
            customer_id=data.customer_id,
            items=data.items,
            discount_percent=data.discount_percent,
            invoice_number=ref,
            transaction_ref=ref,
            notes=data.notes,
            status="unpaid",
        ),
    )

    payment = payment_service.record_payment(
        db,
        business_id,
        user_id,
        PaymentCreate(
            invoice_id=invoice.id,
            amount=invoice.total_amount,
            method=data.method,
            reference=ref,
            payment_date=date.today(),
            notes="Manually confirmed by cashier at POS (no independent bank verification)",
            confirm=True,
        ),
    )

    customer = db.get(Customer, invoice.customer_id)
    invoice_out = InvoiceOut.model_validate(invoice)
    invoice_out.customer_name = customer.name if customer else None
    invoice_out.customer_phone = customer.phone if customer else None
    invoice_out.customer_email = customer.email if customer else None

    payment_out = PaymentOut.model_validate(payment)
    payment_out.invoice_number = invoice.invoice_number
    payment_out.customer_name = customer.name if customer else None

    receipt = Receipt(
        invoice_number=invoice.invoice_number,
        transaction_ref=ref,
        business_name=business.name,
        customer_name=customer.name if customer else None,
        amount=float(invoice.total_amount),
        method=data.method,
        reference=ref,
        payment_date=payment.payment_date,
        status="paid",
    )

    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="pos.checkout",
        category="billing",
        reference=invoice.invoice_number,
        entity_type="invoice",
        entity_id=invoice.id,
        details={
            "method": data.method,
            "amount": float(invoice.total_amount),
            "transaction_ref": ref,
            "manually_confirmed": True,
        },
    )

    return PosCheckoutResponse(
        invoice=invoice_out, payment=payment_out, receipt=receipt
    )
