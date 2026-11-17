from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.repositories.product_repo import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import audit_service, inventory_service


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def _normalize_barcode(value) -> str | None:
    if value is None:
        return None
    barcode = str(value).strip()
    return barcode or None


def _ensure_barcode_available(
    db: Session, business_id: str, barcode: str | None, exclude_id: str | None = None
) -> None:
    """Barcode uniqueness is enforced per business (NULLs are allowed)."""
    if not barcode:
        return
    stmt = select(Product.id).where(
        Product.business_id == business_id, Product.barcode == barcode
    )
    if exclude_id:
        stmt = stmt.where(Product.id != exclude_id)
    if db.execute(stmt).first():
        raise ValidationError(f"Barcode '{barcode}' is already used by another product")


def list_products(db, business_id, query, low_stock_only, skip, limit):
    return ProductRepository(db).search(business_id, query, low_stock_only, skip, limit)


def get_product(db, business_id, product_id) -> Product:
    product = ProductRepository(db).get_for_business(business_id, product_id)
    if not product:
        raise NotFoundError("Product not found")
    return product


def get_by_barcode(db, business_id: str, barcode: str) -> Product:
    normalized = _normalize_barcode(barcode)
    product = None
    if normalized:
        product = db.execute(
            select(Product).where(
                Product.business_id == business_id, Product.barcode == normalized
            )
        ).scalars().first()
    if not product:
        raise NotFoundError("No product found for this barcode")
    return product


def create_product(db, business_id, data: ProductCreate, user_id: str | None = None) -> Product:
    payload = data.model_dump()
    payload["barcode"] = _normalize_barcode(payload.get("barcode"))
    _ensure_barcode_available(db, business_id, payload["barcode"])

    product = Product(business_id=business_id, **payload)
    db.add(product)
    db.flush()

    stock = float(product.stock)
    inventory_service.record_movement(
        db,
        business_id=business_id,
        product=product,
        quantity_change=stock,
        quantity_before=0.0,
        quantity_after=stock,
        reason="initial",
        reference=product.sku,
        user_id=user_id,
        notes="Product created",
    )
    db.flush()

    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="product.create",
        category="product",
        reference=product.sku or product.barcode or product.name,
        entity_type="product",
        entity_id=product.id,
        details={"name": product.name, "barcode": product.barcode, "stock": stock},
    )
    return product


def update_product(
    db, business_id, product_id, data: ProductUpdate, user_id: str | None = None
) -> Product:
    product = get_product(db, business_id, product_id)
    payload = data.model_dump(exclude_unset=True)
    if "barcode" in payload:
        payload["barcode"] = _normalize_barcode(payload["barcode"])
        _ensure_barcode_available(db, business_id, payload["barcode"], exclude_id=product.id)

    before_stock = float(product.stock)
    for key, value in payload.items():
        setattr(product, key, value)
    if getattr(product, "is_service", False):
        product.track_inventory = False
        product.stock = 0
    db.flush()

    after_stock = float(product.stock)
    if abs(after_stock - before_stock) > 1e-9:
        inventory_service.record_movement(
            db,
            business_id=business_id,
            product=product,
            quantity_change=after_stock - before_stock,
            quantity_before=before_stock,
            quantity_after=after_stock,
            reason="correction",
            reference=product.sku,
            user_id=user_id,
            notes="Stock set via product update",
        )
        db.flush()

    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="product.update",
        category="product",
        reference=product.sku or product.barcode or product.name,
        entity_type="product",
        entity_id=product.id,
        details={
            "changed_fields": sorted(payload.keys()),
            "stock_before": before_stock,
            "stock_after": after_stock,
        },
    )
    return product


def delete_product(
    db, business_id, product_id, user_id: str | None = None
) -> None:
    product = get_product(db, business_id, product_id)
    product.is_active = False
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="product.archive",
        category="product",
        reference=product.sku or product.barcode or product.name,
        entity_type="product",
        entity_id=product.id,
        details={"name": product.name},
    )


def low_stock_count(db, business_id) -> int:
    return ProductRepository(db).low_stock_count(business_id)
