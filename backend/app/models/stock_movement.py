from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class StockMovement(BaseModel):
    """Immutable trail of every inventory quantity change."""

    __tablename__ = "stock_movements"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(50), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity_change: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_before: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_after: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    performed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    performed_by_name: Mapped[str] = mapped_column(
        String(150), nullable=False, default="system"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_stock_movements_created_at", "created_at"),
    )
