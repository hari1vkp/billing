from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Payment(BaseModel):
    """A payment against an invoice.

    A payment is only ever considered successful when `status == 'confirmed'`,
    which is set either by an authenticated staff member or by a signature-
    verified webhook — never by a customer clicking a button."""

    __tablename__ = "payments"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[str] = mapped_column(
        Enum("upi", "cash", "card", "bank_transfer", "netbanking", "other", name="payment_method"),
        default="upi",
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "submitted", "confirmed", "failed", "refunded", name="payment_status"),
        default="pending",
        nullable=False,
        index=True,
    )

    # Customer-facing reference (UTR / UPI ref no / bank ref)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    payer_vpa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Ensures stock is decremented at most once per payment.
    stock_adjusted: Mapped[bool] = mapped_column(default=False, nullable=False)


class WebhookEvent(BaseModel):
    """Idempotency ledger for incoming payment-provider webhooks."""

    __tablename__ = "webhook_events"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_provider_event"),
    )
