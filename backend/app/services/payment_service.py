"""Payment workflows.

Key invariant: a payment is NEVER marked successful on a customer's say-so.
Only two paths can confirm a payment:
  1. An authenticated staff member explicitly confirming with a UTR/reference.
  2. A payment-provider webhook with a valid HMAC-SHA256 signature.
"""

import hashlib
import hmac
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.payment import Payment, WebhookEvent
from app.models.product import Product
from app.repositories.payment_repo import PaymentRepository
from app.schemas.payment import ConfirmPaymentRequest, PaymentCreate, PublicPaymentSubmit
from app.services import audit_service, invoice_service, inventory_service


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class PaymentError(Exception):
    pass


def _adjust_stock_once(db: Session, payment: Payment) -> None:
    """Decrement stock for the invoice's inventory items exactly once.

    The stock write and its movement rows share the request transaction, and
    the ``stock_adjusted`` flag keeps the operation idempotent per payment.
    """
    if payment.stock_adjusted:
        return
    invoice = db.get(Invoice, payment.invoice_id)
    reference = invoice.invoice_number if invoice else None
    actor_id = payment.confirmed_by
    actor_name = audit_service.actor_name(db, actor_id)
    items = db.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == payment.invoice_id)
    ).scalars().all()
    for item in items:
        if not item.product_id:
            continue
        product = db.get(Product, item.product_id)
        if product and product.track_inventory:
            before = float(product.stock)
            change = -float(item.quantity)
            after = max(before + change, 0.0)
            product.stock = after
            inventory_service.record_movement(
                db,
                business_id=payment.business_id,
                product=product,
                quantity_change=change,
                quantity_before=before,
                quantity_after=after,
                reason="sale",
                reference=reference,
                user_id=actor_id,
                user_name=actor_name,
                notes=f"Payment {payment.id}",
            )
    payment.stock_adjusted = True
    db.flush()


def _confirm(
    db: Session,
    payment: Payment,
    user_id: str | None,
    reference: str | None = None,
    notes: str | None = None,
) -> Payment:
    if payment.status == "confirmed":
        return payment  # idempotent
    if payment.status in ("refunded", "failed"):
        raise PaymentError(f"Cannot confirm a {payment.status} payment")

    invoice = db.get(Invoice, payment.invoice_id)
    if not invoice or invoice.status == "cancelled":
        raise PaymentError("Invoice is not available for payment")

    payment.status = "confirmed"
    payment.confirmed_at = datetime.now(timezone.utc)
    payment.confirmed_by = user_id
    if reference:
        payment.reference = reference.strip()
    if notes:
        payment.notes = notes
    if not payment.payment_date:
        payment.payment_date = date.today()

    invoice.paid_amount = invoice_service.money(
        float(invoice.paid_amount or 0) + float(payment.amount)
    )
    invoice.balance_amount = invoice_service.money(
        max(float(invoice.total_amount) - float(invoice.paid_amount), 0)
    )
    invoice_service.recompute_status(invoice)
    _adjust_stock_once(db, payment)
    db.flush()
    audit_service.log_activity(
        db,
        payment.business_id,
        user_id=user_id,
        action="payment.confirm",
        category="payment",
        reference=payment.reference or invoice.invoice_number,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "amount": float(payment.amount),
            "method": payment.method,
            "invoice_number": invoice.invoice_number,
        },
    )
    return payment


# ---------------------------------------------------------------------------
# Staff / authenticated flows
# ---------------------------------------------------------------------------
def list_payments(db, business_id, **kwargs):
    return PaymentRepository(db).list_detailed(business_id, **kwargs)


def get_payment(db, business_id, payment_id) -> Payment:
    payment = PaymentRepository(db).get_for_business(business_id, payment_id)
    if not payment:
        raise NotFoundError("Payment not found")
    return payment


def get_payments_for_invoice(db, business_id, invoice_id) -> list[Payment]:
    return list(
        db.execute(
            select(Payment).where(
                Payment.business_id == business_id, Payment.invoice_id == invoice_id
            )
        ).scalars().all()
    )


def record_payment(db, business_id, user_id, data: PaymentCreate) -> Payment:
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == data.invoice_id, Invoice.business_id == business_id
        )
    ).scalar_one_or_none()
    if not invoice:
        raise NotFoundError("Invoice not found")
    if invoice.status == "cancelled":
        raise PaymentError("Cannot record payment against a cancelled invoice")
    if data.amount <= 0:
        raise ValidationError("Amount must be positive")
    if data.confirm and invoice.status == "paid":
        raise PaymentError("Invoice is already fully paid")

    payment = Payment(
        business_id=business_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        amount=data.amount,
        method=data.method,
        status="pending",
        reference=data.reference,
        payer_vpa=data.payer_vpa,
        payment_date=data.payment_date,
        notes=data.notes,
    )
    db.add(payment)
    db.flush()
    if data.confirm:
        _confirm(db, payment, user_id, data.reference, data.notes)
    return payment


def confirm_payment(
    db, business_id, payment_id, user_id, data: ConfirmPaymentRequest
) -> Payment:
    payment = get_payment(db, business_id, payment_id)
    return _confirm(db, payment, user_id, data.reference, data.notes)


def fail_payment(db, business_id, payment_id) -> Payment:
    payment = get_payment(db, business_id, payment_id)
    payment.status = "failed"
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        action="payment.fail",
        category="payment",
        reference=payment.reference,
        entity_type="payment",
        entity_id=payment.id,
        details={"amount": float(payment.amount)},
    )
    return payment


def refund_payment(db, business_id, payment_id, user_id) -> Payment:
    payment = get_payment(db, business_id, payment_id)
    if payment.status != "confirmed":
        raise PaymentError("Only confirmed payments can be refunded")
    invoice = db.get(Invoice, payment.invoice_id)
    invoice.paid_amount = invoice_service.money(
        max(float(invoice.paid_amount) - float(payment.amount), 0)
    )
    invoice.balance_amount = invoice_service.money(
        max(float(invoice.total_amount) - float(invoice.paid_amount), 0)
    )
    invoice_service.recompute_status(invoice)
    payment.status = "refunded"
    payment.confirmed_by = user_id
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="payment.refund",
        category="payment",
        reference=payment.reference,
        entity_type="payment",
        entity_id=payment.id,
        details={"amount": float(payment.amount), "invoice": invoice.invoice_number},
    )
    return payment


# ---------------------------------------------------------------------------
# Public (customer-facing) flow — deliberately cannot confirm
# ---------------------------------------------------------------------------
def submit_public_payment(db, public_token: str, data: PublicPaymentSubmit) -> Payment:
    invoice = invoice_service.get_by_public_token(db, public_token)
    if not invoice or invoice.status in ("cancelled", "draft"):
        raise NotFoundError("Invoice is not available for payment")
    if invoice.status == "paid":
        raise PaymentError("This invoice has already been paid")
    balance = float(invoice.balance_amount or invoice.total_amount)
    if float(data.amount) > balance + 0.01:
        raise PaymentError(f"Amount cannot exceed the outstanding balance of {balance:.2f}")

    payment = Payment(
        business_id=invoice.business_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        amount=data.amount,
        method=data.method,
        status="submitted",  # NOT confirmed — awaiting verification
        reference=data.reference,
        payer_vpa=data.payer_vpa,
        payment_date=date.today(),
        notes=(data.notes or "") + " [submitted via public payment link]",
    )
    db.add(payment)
    db.flush()
    audit_service.log_activity(
        db,
        invoice.business_id,
        user_name="customer",
        action="payment.submitted",
        category="payment",
        reference=data.reference,
        entity_type="payment",
        entity_id=payment.id,
        details={"amount": float(payment.amount), "invoice": invoice.invoice_number},
    )
    return payment


# ---------------------------------------------------------------------------
# Provider webhook flow
# ---------------------------------------------------------------------------
def verify_webhook_signature(
    raw_body: bytes, signature: str | None, secret: str | None = None
) -> bool:
    if not signature:
        return False
    secret = secret or settings.PAYMENT_WEBHOOK_SECRET
    supplied = signature.strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied.strip().lower())


def process_webhook(
    db: Session,
    provider: str,
    event_id: str,
    payload: dict,
    raw_body: bytes,
    signature: str | None,
    secret: str | None = None,
) -> WebhookEvent:
    secret = secret or settings.PAYMENT_WEBHOOK_SECRET
    repo = PaymentRepository(db)

    # Idempotency: record/return the event once.
    existing = repo.get_webhook_event(provider, event_id)
    if existing:
        return existing

    event = WebhookEvent(
        provider=provider, event_id=event_id, payload=payload, processed=False
    )
    repo.add_webhook_event(event)

    if not verify_webhook_signature(raw_body, signature, secret):
        event.error = "Invalid signature"
        db.flush()
        raise PaymentError("Invalid webhook signature")

    data = payload.get("data") or payload
    status = str(data.get("status", "")).lower()
    reference = data.get("reference") or data.get("utr") or data.get("transaction_ref")
    invoice_number = data.get("invoice_number")
    amount = data.get("amount")

    payment = None
    if reference:
        payment = db.execute(
            select(Payment).where(
                Payment.reference == str(reference),
                Payment.status.in_(["pending", "submitted"]),
            )
        ).scalar_one_or_none()
    if payment is None and invoice_number:
        q = select(Payment).join(Invoice, Invoice.id == Payment.invoice_id).where(
            Invoice.invoice_number == str(invoice_number),
            Payment.status.in_(["pending", "submitted"]),
        )
        if amount is not None:
            q = q.where(Payment.amount == float(amount))
        payment = db.execute(q.order_by(Payment.created_at.desc())).scalar_one_or_none()

    try:
        if payment is None:
            event.error = "No matching pending payment found"
        elif status in ("success", "successful", "captured", "paid", "confirmed"):
            _confirm(db, payment, None, str(reference) if reference else None,
                     f"Confirmed via {provider} webhook")
            event.processed = True
        elif status in ("failed", "failure", "declined"):
            payment.status = "failed"
            event.processed = True
        else:
            event.error = f"Unhandled payment status: {status}"
    except PaymentError as exc:
        event.error = str(exc)

    db.flush()

    if payment:
        audit_service.log_activity(
            db,
            payment.business_id,
            user_name="system",
            action="payment.webhook",
            category="payment",
            reference=event_id,
            entity_type="webhook",
            entity_id=event.id,
            details={
                "provider": provider,
                "status": status,
                "processed": bool(event.processed),
                "error": event.error,
                "payment_id": payment.id,
            },
        )
        if event.processed and status in ("failed", "failure", "declined"):
            audit_service.log_activity(
                db,
                payment.business_id,
                user_name="system",
                action="payment.fail",
                category="payment",
                reference=payment.reference,
                entity_type="payment",
                entity_id=payment.id,
                details={"amount": float(payment.amount), "provider": provider},
            )
    return event
