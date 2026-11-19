from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Invoice(BaseModel):
    __tablename__ = "invoices"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    # Stable per-transaction reference used as the UPI QR `tr` parameter.
    # Backfilled from invoice_number for pre-existing rows by the startup migration.
    transaction_ref: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(
            "draft",
            "unpaid",
            "partially_paid",
            "paid",
            "cancelled",
            name="invoice_status",
        ),
        default="unpaid",
        nullable=False,
        index=True,
    )

    # Amounts (all in business currency)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    discount_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    taxable_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    balance_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )

    # "retail" (default) or "wholesale". Persisted so draft edits and completed
    # bills keep the pricing mode they were created with.
    pricing_mode: Mapped[str] = mapped_column(
        String(16), default="retail", nullable=False, index=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="InvoiceItem.sort_order",
    )

    __table_args__ = (
        # Invoice numbers are unique within a business (enforced at DB level).
        UniqueConstraint(
            "business_id", "invoice_number", name="uq_business_invoice_number"
        ),
    )


class InvoiceItem(BaseModel):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    discount_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    # Snapshot of the product discount applied at bill time (0 in retail mode).
    wholesale_discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    taxable_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    gst_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="items")
