"""General-purpose supplier management models.

Every table is tenant-scoped by ``business_id``. Supplier-product links never
create inventory products: they either point at an existing BillFlow product or
carry a free-text ``custom_name``.
"""

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Supplier(BaseModel):
    """A supplier / vendor / company we source goods from."""

    __tablename__ = "suppliers"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    whatsapp: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free text — categories are discovered from stored rows, never hardcoded.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    brands: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SupplierProduct(BaseModel):
    """A product (or custom item) offered by a supplier.

    ``product_id`` is nullable: when it is set it MUST reference an existing
    BillFlow product in the same business. Otherwise ``custom_name`` describes
    the item and no inventory product is created.
    """

    __tablename__ = "supplier_products"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[str] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    custom_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Optional per-supplier unit override; falls back to the product's unit.
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(80), nullable=True)
    supplier_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_supplier_products_supplier_product", "supplier_id", "product_id"),
    )


class PurchaseReminderList(BaseModel):
    """A reminder list for a supplier visit (pending until converted)."""

    __tablename__ = "purchase_reminder_lists"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[str] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PurchaseReminderItem(BaseModel):
    """One line on a reminder list.

    Marking ``is_purchased`` is purely informational and never moves stock.
    """

    __tablename__ = "purchase_reminder_items"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    list_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_reminder_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_purchased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SupplierVisit(BaseModel):
    """Notes and follow-ups from a supplier visit."""

    __tablename__ = "supplier_visits"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[str] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    discussion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_discussed: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_requested: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_supplier_visits_supplier_date", "supplier_id", "visit_date"),
    )


class SupplierPurchase(BaseModel):
    """A purchase order created by converting a reminder list."""

    __tablename__ = "supplier_purchases"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[str] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    purchase_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    reminder_list_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_reminder_lists.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SupplierPurchaseItem(BaseModel):
    """A product-backed line of a converted purchase.

    Custom-name reminder items are not stocked and are carried into the
    purchase ``notes`` instead of becoming purchase items.
    """

    __tablename__ = "supplier_purchase_items"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("supplier_purchases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    reminder_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_reminder_items.id", ondelete="SET NULL"), nullable=True
    )
