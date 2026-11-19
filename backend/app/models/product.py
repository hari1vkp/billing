from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Product(BaseModel):
    """A product (inventory tracked) or a service (no inventory)."""

    __tablename__ = "products"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsn_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=18.0, nullable=False)
    stock: Mapped[float] = mapped_column(Numeric(14, 3), default=0.0, nullable=False)
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_service: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    low_stock_threshold: Mapped[float] = mapped_column(
        Numeric(14, 3), default=10.0, nullable=False
    )
    discount_type: Mapped[str] = mapped_column(
        String(16), default="none", nullable=False
    )
    discount_value: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0.0, nullable=False
    )
    # Wholesale selling price is derived from `price`, never stored here.
    wholesale_discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
