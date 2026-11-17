"""Inventory adjustments and the stock movement history."""

from datetime import date

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.schemas.inventory import StockAdjustCreate
from app.services import audit_service

# Restrictions applied to cashiers/staff. Owners are unrestricted.
STAFF_ALLOWED_REASONS = {"found", "damaged", "return", "correction"}
STAFF_MAX_ABS_CHANGE = 20.0


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def record_movement(
    db: Session,
    *,
    business_id: str,
    product: Product,
    quantity_change: float,
    quantity_before: float,
    quantity_after: float,
    reason: str,
    reference: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    notes: str | None = None,
) -> StockMovement:
    """Create (but do not commit) a stock movement row for an actor."""
    movement = StockMovement(
        business_id=business_id,
        product_id=product.id,
        product_name=product.name,
        sku=product.sku,
        barcode=product.barcode,
        quantity_change=quantity_change,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        reason=reason,
        reference=reference,
        performed_by=user_id,
        performed_by_name=audit_service.actor_name(db, user_id, user_name),
        notes=notes,
    )
    db.add(movement)
    return movement


def adjust_stock(
    db: Session,
    business_id: str,
    user: User,
    data: StockAdjustCreate,
) -> StockMovement:
    """Apply a manual stock delta and record who did it, in one transaction."""
    quantity_change = float(data.quantity_change)
    if quantity_change == 0:
        raise ValidationError("quantity_change must be a non-zero number")

    reason = (data.reason or "").strip().lower()
    if not reason:
        raise ValidationError("reason is required")
    if user.role == "staff":
        if reason not in STAFF_ALLOWED_REASONS:
            raise ValidationError(
                "Staff may only adjust stock for: "
                + ", ".join(sorted(STAFF_ALLOWED_REASONS))
            )
        if abs(quantity_change) > STAFF_MAX_ABS_CHANGE:
            raise ValidationError("Staff may only adjust up to 20 units at a time")

    product = db.execute(
        select(Product).where(
            Product.id == data.product_id, Product.business_id == business_id
        )
    ).scalars().first()
    if not product:
        raise NotFoundError("Product not found")

    before = float(product.stock)
    after = before + quantity_change
    if after < 0:
        raise ValidationError("Stock cannot go below zero")
    product.stock = after

    movement = record_movement(
        db,
        business_id=business_id,
        product=product,
        quantity_change=quantity_change,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        reference=product.sku,
        user_id=user.id,
        user_name=user.full_name,
        notes=data.notes,
    )
    db.flush()

    audit_service.log_activity(
        db,
        business_id,
        user_id=user.id,
        action="stock.adjust",
        category="stock",
        reference=product.sku,
        entity_type="product",
        entity_id=product.id,
        details={
            "product_name": product.name,
            "quantity_change": quantity_change,
            "quantity_before": before,
            "quantity_after": after,
            "reason": reason,
        },
    )
    return movement


def list_movements(
    db: Session,
    business_id: str,
    *,
    product_id: str | None = None,
    reason: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    skip: int = 0,
    limit: int = 20,
):
    stmt = select(StockMovement).where(StockMovement.business_id == business_id)
    if product_id:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if reason:
        stmt = stmt.where(StockMovement.reason == reason.strip().lower())
    if from_date:
        stmt = stmt.where(cast(StockMovement.created_at, Date) >= from_date)
    if to_date:
        stmt = stmt.where(cast(StockMovement.created_at, Date) <= to_date)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = list(
        db.execute(
            stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
    )
    return items, total
