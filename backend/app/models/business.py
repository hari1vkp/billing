from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Business(BaseModel):
    """A tenant. All business data is isolated by business_id."""

    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # UPI configuration
    upi_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upi_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    # Per-tenant invoice numbering sequence
    invoice_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Invoice-level settings
    default_gst_rate: Mapped[float] = mapped_column(
        Numeric(5, 2), default=18.0, nullable=False
    )
    invoice_prefix: Mapped[str] = mapped_column(String(20), default="INV", nullable=False)
    invoice_footer: Mapped[str | None] = mapped_column(Text, nullable=True)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
