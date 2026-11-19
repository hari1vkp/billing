"""General-purpose supplier management service.

Design rules enforced here:
  * every lookup is scoped to ``business_id``;
  * supplier-product links reference an EXISTING BillFlow product or a custom
    name and never insert into ``products``;
  * marking a reminder item purchased only flips ``is_purchased``;
  * conversion is one transaction and increases stock exclusively through the
    existing ``inventory_service.record_movement`` receiving path.
"""

import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.supplier import (
    PurchaseReminderItem,
    PurchaseReminderList,
    Supplier,
    SupplierProduct,
    SupplierPurchase,
    SupplierPurchaseItem,
    SupplierVisit,
)
from app.models.user import User
from app.schemas.supplier import (
    ConvertToPurchaseIn,
    QuickSaveIn,
    ReminderItemCreate,
    ReminderItemUpdate,
    ReminderListCreate,
    ReminderListUpdate,
    SupplierCreate,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierPurchaseItemOut,
    SupplierPurchaseOut,
    SupplierUpdate,
    VisitCreate,
    VisitUpdate,
)
from app.services import audit_service, inventory_service


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class ConflictError(Exception):
    pass


class RelationshipError(ValidationError):
    """A reminder item's product_id is not linked to its list's supplier."""


def _parse_description_metadata(description: str | None) -> dict[str, str | None]:
    """Read explicitly stored catalogue metadata from a product description.

    The importer encodes metadata as ``Label: value | Label: value`` and the
    catalogue prompt uses the same labels, but a JSON object is accepted too.
    Values are returned ONLY when the label/key is actually present — nothing
    is guessed from the product name or from free-form prose.
    """
    result: dict[str, str | None] = {
        "brand": None,
        "category": None,
        "variant": None,
        "size_pack": None,
    }
    if not description or not str(description).strip():
        return result

    text = str(description).strip()

    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            aliases = {
                "brand": ("brand",),
                "category": ("category",),
                "variant": ("variant",),
                "size_pack": ("size_pack", "size", "size_pack_size", "size / pack size"),
            }
            lowered = {str(k).strip().lower(): v for k, v in payload.items()}
            for key, names in aliases.items():
                for name in names:
                    value = lowered.get(name)
                    if value is not None and str(value).strip():
                        result[key] = str(value).strip()
                        break
            return result

    aliases = {
        "brand": ("brand",),
        "category": ("category",),
        "variant": ("variant",),
        "size_pack": ("size", "size_pack", "size / pack size", "pack size"),
    }
    for segment in re.split(r"[|\n]", text):
        if ":" not in segment:
            continue
        label, _, value = segment.partition(":")
        label = label.strip().lower()
        value = value.strip()
        if not value:
            continue
        for key, names in aliases.items():
            if label in names and result[key] is None:
                result[key] = value
    return result


def _money(value) -> float:
    return float(
        Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


# ---------------------------------------------------------------------------
# Supplier CRUD / discovery
# ---------------------------------------------------------------------------
def _get_supplier(db: Session, business_id: str, supplier_id: str) -> Supplier:
    supplier = db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.business_id == business_id
        )
    ).scalars().first()
    if not supplier:
        raise NotFoundError("Supplier not found")
    return supplier


def list_suppliers(
    db: Session,
    business_id: str,
    *,
    q: str | None = None,
    category: str | None = None,
    product_type: str | None = None,
    is_active: bool | None = None,
    sort: str | None = None,
    order: str | None = None,
    skip: int = 0,
    limit: int = 20,
):
    stmt = select(Supplier).where(Supplier.business_id == business_id)
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active.is_(is_active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Supplier.name.ilike(like),
                Supplier.contact_person.ilike(like),
                Supplier.phone.ilike(like),
                Supplier.category.ilike(like),
                Supplier.brands.ilike(like),
            )
        )
    if category:
        stmt = stmt.where(Supplier.category.ilike(f"%{category.strip()}%"))
    if product_type:
        # A supplier matches when a linked product's name (or custom name)
        # matches the requested product type/brand text.
        match = f"%{product_type.strip()}%"
        stmt = stmt.where(
            Supplier.id.in_(
                select(SupplierProduct.supplier_id).where(
                    SupplierProduct.business_id == business_id,
                    or_(
                        SupplierProduct.custom_name.ilike(match),
                        SupplierProduct.product_id.in_(
                            select(Product.id).where(Product.name.ilike(match))
                        ),
                    ),
                )
            )
        )

    sort_columns = {
        "name": Supplier.name,
        "category": Supplier.category,
        "created_at": Supplier.created_at,
        "updated_at": Supplier.updated_at,
    }
    column = sort_columns.get((sort or "name").lower(), Supplier.name)
    direction = (order or "asc").lower()
    stmt = stmt.order_by(
        column.desc() if direction == "desc" else column.asc(), Supplier.id.asc()
    )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    suppliers = list(db.execute(stmt.offset(skip).limit(limit)).scalars().all())

    counts = dict(
        db.execute(
            select(SupplierProduct.supplier_id, func.count(SupplierProduct.id))
            .where(SupplierProduct.business_id == business_id)
            .group_by(SupplierProduct.supplier_id)
        ).all()
    )
    for supplier in suppliers:
        supplier.product_count = counts.get(supplier.id, 0)
    return suppliers, total


def discover_categories(db: Session, business_id: str) -> dict:
    """Return distinct values derived from rows this business actually stored."""
    rows = db.execute(
        select(Supplier.category, Supplier.brands).where(
            Supplier.business_id == business_id
        )
    ).all()
    categories = sorted({r[0].strip() for r in rows if r[0] and r[0].strip()})
    brands = sorted(
        {
            part.strip()
            for r in rows
            if r[1]
            for part in str(r[1]).split(",")
            if part.strip()
        }
    )
    product_rows = db.execute(
        select(SupplierProduct.custom_name, Product.name)
        .outerjoin(Product, SupplierProduct.product_id == Product.id)
        .where(SupplierProduct.business_id == business_id)
    ).all()
    product_types = sorted(
        {
            value.strip()
            for custom_name, product_name in product_rows
            for value in (product_name or custom_name,)
            if value and value.strip()
        }
    )
    return {"categories": categories, "brands": brands, "product_types": product_types}


def get_supplier(db: Session, business_id: str, supplier_id: str) -> Supplier:
    return _get_supplier(db, business_id, supplier_id)


def get_supplier_detail(db: Session, business_id: str, supplier_id: str):
    from app.schemas.supplier import SupplierDetail

    supplier = _get_supplier(db, business_id, supplier_id)
    detail = SupplierDetail.model_validate(supplier)
    # Use the enriched card DTO so the profile's Products tab can show the real
    # product name, brand/category, variant/size and unit — not just a bare id.
    detail.products = [
        supplier_product_card_out(db, link)
        for link in list_supplier_products(db, business_id, supplier_id)
    ]
    detail.reminder_lists = [
        reminder_list_out(db, item)
        for item in list_reminder_lists(db, business_id, supplier_id)
    ]
    detail.visits = [visit_out(v) for v in list_visits(db, business_id, supplier_id)]
    return detail


def create_supplier(
    db: Session, business_id: str, data: SupplierCreate, user_id: str | None = None
) -> Supplier:
    supplier = Supplier(business_id=business_id, **data.model_dump())
    db.add(supplier)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.create",
        category="supplier",
        reference=supplier.phone,
        entity_type="supplier",
        entity_id=supplier.id,
        details={"name": supplier.name, "category": supplier.category},
    )
    return supplier


def update_supplier(
    db: Session,
    business_id: str,
    supplier_id: str,
    data: SupplierUpdate,
    user_id: str | None = None,
) -> Supplier:
    supplier = _get_supplier(db, business_id, supplier_id)
    payload = data.model_dump(exclude_unset=True)
    was_active = supplier.is_active
    for key, value in payload.items():
        setattr(supplier, key, value)
    db.flush()
    action = "supplier.update"
    if was_active and supplier.is_active is False:
        action = "supplier.deactivate"
    elif not was_active and supplier.is_active is True:
        action = "supplier.reactivate"
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action=action,
        category="supplier",
        reference=supplier.phone,
        entity_type="supplier",
        entity_id=supplier.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return supplier


def deactivate_supplier(
    db: Session, business_id: str, supplier_id: str, user_id: str | None = None
) -> Supplier:
    supplier = _get_supplier(db, business_id, supplier_id)
    supplier.is_active = False
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.deactivate",
        category="supplier",
        reference=supplier.phone,
        entity_type="supplier",
        entity_id=supplier.id,
        details={"name": supplier.name},
    )
    return supplier


# ---------------------------------------------------------------------------
# Supplier-product links
# ---------------------------------------------------------------------------
def supplier_product_out(link: SupplierProduct):
    from app.schemas.supplier import SupplierProductOut

    return SupplierProductOut.model_validate(link)


def supplier_product_card_out(db: Session, link: SupplierProduct):
    """Build a reminder-card DTO from the link + its product (never the global catalogue)."""
    from app.schemas.supplier import SupplierProductCardOut

    product = None
    if link.product_id:
        product = db.execute(
            select(Product).where(
                Product.id == link.product_id, Product.business_id == link.business_id
            )
        ).scalars().first()

    meta = _parse_description_metadata(product.description if product else None)
    product_unit = str(product.unit) if product and product.unit else None
    resolved_unit = link.unit or product_unit

    return SupplierProductCardOut(
        id=link.id,
        business_id=link.business_id,
        supplier_id=link.supplier_id,
        product_id=link.product_id,
        custom_name=link.custom_name,
        unit=resolved_unit,
        supplier_sku=link.supplier_sku,
        supplier_price=link.supplier_price,
        notes=link.notes,
        created_at=link.created_at,
        updated_at=link.updated_at,
        product_name=product.name if product else None,
        product_brand=meta["brand"],
        product_category=meta["category"],
        product_variant=meta["variant"],
        product_size_pack=meta["size_pack"],
        product_unit=product_unit,
    )


def _get_link(
    db: Session, business_id: str, supplier_id: str, link_id: str
) -> SupplierProduct:
    link = db.execute(
        select(SupplierProduct).where(
            SupplierProduct.id == link_id,
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.business_id == business_id,
        )
    ).scalars().first()
    if not link:
        raise NotFoundError("Supplier product not found")
    return link


def _validate_product(db: Session, business_id: str, product_id: str) -> Product:
    product = db.execute(
        select(Product).where(
            Product.id == product_id, Product.business_id == business_id
        )
    ).scalars().first()
    if not product:
        raise ValidationError("Linked BillFlow product not found")
    return product


def _validate_supplier_product_link(
    db: Session, business_id: str, supplier_id: str, product_id: str
) -> SupplierProduct | None:
    """Require a link to this exact supplier, not merely to any supplier.

    New reminder items must reference a product currently supplied by THIS
    supplier. Historical reminder items are never re-validated when edited,
    so unlinking a product later cannot break saved records.
    """
    links = db.execute(
        select(SupplierProduct).where(
            SupplierProduct.business_id == business_id,
            SupplierProduct.product_id == product_id,
        )
    ).scalars().all()
    if not links:
        raise RelationshipError("Product is not linked to this supplier")
    for link in links:
        if link.supplier_id == supplier_id:
            return link
    raise RelationshipError("Product is not linked to this supplier")


def list_supplier_products(db: Session, business_id: str, supplier_id: str):
    _get_supplier(db, business_id, supplier_id)
    return list(
        db.execute(
            select(SupplierProduct)
            .where(
                SupplierProduct.business_id == business_id,
                SupplierProduct.supplier_id == supplier_id,
            )
            .order_by(SupplierProduct.created_at.asc(), SupplierProduct.id.asc())
        ).scalars().all()
    )


def add_supplier_product(
    db: Session,
    business_id: str,
    supplier_id: str,
    data: SupplierProductCreate,
    user_id: str | None = None,
) -> SupplierProduct:
    _get_supplier(db, business_id, supplier_id)
    payload = data.model_dump()
    if payload.get("product_id"):
        _validate_product(db, business_id, payload["product_id"])
        duplicate = db.execute(
            select(SupplierProduct.id).where(
                SupplierProduct.business_id == business_id,
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == payload["product_id"],
            )
        ).first()
        if duplicate:
            raise ValidationError("This product is already linked to this supplier")
    elif not payload.get("custom_name"):
        raise ValidationError("A product_id or custom_name is required")
    link = SupplierProduct(
        business_id=business_id, supplier_id=supplier_id, **payload
    )
    db.add(link)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.product.add",
        category="supplier",
        reference=payload.get("product_id") or payload.get("custom_name"),
        entity_type="supplier_product",
        entity_id=link.id,
        details={"supplier_id": supplier_id},
    )
    return link


def update_supplier_product(
    db: Session,
    business_id: str,
    supplier_id: str,
    link_id: str,
    data: SupplierProductUpdate,
    user_id: str | None = None,
) -> SupplierProduct:
    link = _get_link(db, business_id, supplier_id, link_id)
    payload = data.model_dump(exclude_unset=True)
    product_id = payload.get("product_id", link.product_id)
    custom_name = payload.get("custom_name", link.custom_name)
    if product_id:
        _validate_product(db, business_id, product_id)
        if product_id != link.product_id:
            duplicate = db.execute(
                select(SupplierProduct.id).where(
                    SupplierProduct.business_id == business_id,
                    SupplierProduct.supplier_id == supplier_id,
                    SupplierProduct.product_id == product_id,
                )
            ).first()
            if duplicate:
                raise ValidationError("This product is already linked to this supplier")
    elif not custom_name:
        raise ValidationError("A product_id or custom_name is required")
    for key, value in payload.items():
        setattr(link, key, value)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.product.update",
        category="supplier",
        entity_type="supplier_product",
        entity_id=link.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return link


def delete_supplier_product(
    db: Session,
    business_id: str,
    supplier_id: str,
    link_id: str,
    user_id: str | None = None,
) -> None:
    link = _get_link(db, business_id, supplier_id, link_id)
    db.delete(link)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.product.remove",
        category="supplier",
        entity_type="supplier_product",
        entity_id=link_id,
        details={"supplier_id": supplier_id},
    )


# ---------------------------------------------------------------------------
# Purchase reminder lists and items
# ---------------------------------------------------------------------------
def _get_reminder_list(
    db: Session, business_id: str, list_id: str
) -> PurchaseReminderList:
    reminder_list = db.execute(
        select(PurchaseReminderList)
        .join(Supplier, PurchaseReminderList.supplier_id == Supplier.id)
        .where(
            PurchaseReminderList.id == list_id,
            PurchaseReminderList.business_id == business_id,
            Supplier.business_id == business_id,
        )
    ).scalars().first()
    if not reminder_list:
        raise NotFoundError("Reminder list not found")
    return reminder_list


def reminder_item_out(item: PurchaseReminderItem):
    from app.schemas.supplier import ReminderItemOut

    return ReminderItemOut.model_validate(item)


def reminder_list_out(db: Session, reminder_list: PurchaseReminderList):
    from app.schemas.supplier import ReminderListOut

    out = ReminderListOut.model_validate(reminder_list)
    out.items = [
        reminder_item_out(item)
        for item in list_reminder_items(db, reminder_list.business_id, reminder_list.id)
    ]
    return out


def list_reminder_lists(db: Session, business_id: str, supplier_id: str):
    _get_supplier(db, business_id, supplier_id)
    return list(
        db.execute(
            select(PurchaseReminderList)
            .where(
                PurchaseReminderList.business_id == business_id,
                PurchaseReminderList.supplier_id == supplier_id,
            )
            .order_by(PurchaseReminderList.created_at.desc(), PurchaseReminderList.id.asc())
        ).scalars().all()
    )


def create_reminder_list(
    db: Session,
    business_id: str,
    supplier_id: str,
    data: ReminderListCreate,
    user_id: str | None = None,
) -> PurchaseReminderList:
    _get_supplier(db, business_id, supplier_id)
    reminder_list = PurchaseReminderList(
        business_id=business_id,
        supplier_id=supplier_id,
        created_by=user_id,
        **data.model_dump(),
    )
    db.add(reminder_list)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.create",
        category="supplier",
        reference=reminder_list.title,
        entity_type="purchase_reminder_list",
        entity_id=reminder_list.id,
        details={"supplier_id": supplier_id},
    )
    return reminder_list


def update_reminder_list(
    db: Session,
    business_id: str,
    list_id: str,
    data: ReminderListUpdate,
    user_id: str | None = None,
) -> PurchaseReminderList:
    reminder_list = _get_reminder_list(db, business_id, list_id)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(reminder_list, key, value)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.update",
        category="supplier",
        entity_type="purchase_reminder_list",
        entity_id=list_id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return reminder_list


def get_reminder_list(db: Session, business_id: str, list_id: str):
    return reminder_list_out(db, _get_reminder_list(db, business_id, list_id))


def list_reminder_items(db: Session, business_id: str, list_id: str):
    _get_reminder_list(db, business_id, list_id)
    return list(
        db.execute(
            select(PurchaseReminderItem)
            .where(
                PurchaseReminderItem.business_id == business_id,
                PurchaseReminderItem.list_id == list_id,
            )
            .order_by(
                PurchaseReminderItem.created_at.asc(), PurchaseReminderItem.id.asc()
            )
        ).scalars().all()
    )


def _get_reminder_item(
    db: Session, business_id: str, list_id: str, item_id: str
) -> PurchaseReminderItem:
    _get_reminder_list(db, business_id, list_id)
    item = db.execute(
        select(PurchaseReminderItem).where(
            PurchaseReminderItem.id == item_id,
            PurchaseReminderItem.list_id == list_id,
            PurchaseReminderItem.business_id == business_id,
        )
    ).scalars().first()
    if not item:
        raise NotFoundError("Reminder item not found")
    return item


def find_existing_reminder_item(
    db: Session, business_id: str, list_id: str, product_id: str | None
) -> PurchaseReminderItem | None:
    """Find an existing item for a product on a list (endpoint-level dedupe)."""
    if not product_id:
        return None
    _get_reminder_list(db, business_id, list_id)
    return db.execute(
        select(PurchaseReminderItem).where(
            PurchaseReminderItem.business_id == business_id,
            PurchaseReminderItem.list_id == list_id,
            PurchaseReminderItem.product_id == product_id,
        )
    ).scalars().first()


def add_reminder_item(
    db: Session,
    business_id: str,
    list_id: str,
    data: ReminderItemCreate,
    user_id: str | None = None,
) -> PurchaseReminderItem:
    reminder_list = _get_reminder_list(db, business_id, list_id)
    payload = data.model_dump()
    product_id = payload.get("product_id")
    if product_id:
        _validate_product(db, business_id, product_id)
        _validate_supplier_product_link(
            db, business_id, reminder_list.supplier_id, product_id
        )
    item = PurchaseReminderItem(
        business_id=business_id, list_id=reminder_list.id, **payload
    )
    db.add(item)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.item.add",
        category="supplier",
        reference=item.name,
        entity_type="purchase_reminder_item",
        entity_id=item.id,
        details={"list_id": list_id},
    )
    return item


def update_reminder_item(
    db: Session,
    business_id: str,
    list_id: str,
    item_id: str,
    data: ReminderItemUpdate,
    user_id: str | None = None,
) -> PurchaseReminderItem:
    # NOTE: this only mutates reminder-item fields. Stock is NEVER touched here.
    item = _get_reminder_item(db, business_id, list_id, item_id)
    reminder_list = _get_reminder_list(db, business_id, list_id)
    payload = data.model_dump(exclude_unset=True)
    requested_product_id = payload.get("product_id")
    # Historical items stay editable even if their product was later unlinked.
    # Only a NEW product assignment is validated against current links.
    if requested_product_id and requested_product_id != item.product_id:
        _validate_product(db, business_id, requested_product_id)
        _validate_supplier_product_link(
            db, business_id, reminder_list.supplier_id, requested_product_id
        )
    for key, value in payload.items():
        setattr(item, key, value)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.item.update",
        category="supplier",
        reference=item.name,
        entity_type="purchase_reminder_item",
        entity_id=item.id,
        details={"changed_fields": sorted(payload.keys()), "is_purchased": item.is_purchased},
    )
    return item


def delete_reminder_item(
    db: Session,
    business_id: str,
    list_id: str,
    item_id: str,
    user_id: str | None = None,
) -> None:
    item = _get_reminder_item(db, business_id, list_id, item_id)
    db.delete(item)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.item.remove",
        category="supplier",
        entity_type="purchase_reminder_item",
        entity_id=item_id,
    )


def delete_reminder_list(
    db: Session, business_id: str, list_id: str, user_id: str | None = None
) -> None:
    """Delete a reminder list together with all of its items.

    Purely a reminder operation: stock is never read or written here.
    """
    reminder_list = _get_reminder_list(db, business_id, list_id)
    items = db.execute(
        select(PurchaseReminderItem).where(
            PurchaseReminderItem.business_id == business_id,
            PurchaseReminderItem.list_id == list_id,
        )
    ).scalars().all()
    for item in items:
        db.delete(item)
    db.delete(reminder_list)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.remove",
        category="supplier",
        reference=reminder_list.title,
        entity_type="purchase_reminder_list",
        entity_id=list_id,
        details={"item_count": len(items)},
    )


def carry_forward_reminder_list(
    db: Session, business_id: str, list_id: str, user_id: str | None = None
):
    """Create a new pending list holding only this list's unfinished items."""
    source = _get_reminder_list(db, business_id, list_id)
    pending = db.execute(
        select(PurchaseReminderItem)
        .where(
            PurchaseReminderItem.business_id == business_id,
            PurchaseReminderItem.list_id == list_id,
            PurchaseReminderItem.is_purchased.is_(False),
        )
        .order_by(PurchaseReminderItem.created_at.asc(), PurchaseReminderItem.id.asc())
    ).scalars().all()

    new_list = PurchaseReminderList(
        business_id=business_id,
        supplier_id=source.supplier_id,
        title=f"{source.title} (next visit)",
        status="pending",
        notes=source.notes,
        created_by=user_id,
    )
    db.add(new_list)
    db.flush()

    for item in pending:
        db.add(
            PurchaseReminderItem(
                business_id=business_id,
                list_id=new_list.id,
                product_id=item.product_id,
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                expected_price=item.expected_price,
                notes=item.notes,
                is_purchased=False,
            )
        )
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.reminder.carry_forward",
        category="supplier",
        reference=new_list.title,
        entity_type="purchase_reminder_list",
        entity_id=new_list.id,
        details={"source_list_id": list_id, "item_count": len(pending)},
    )
    return reminder_list_out(db, new_list)


def quick_save_reminder(
    db: Session,
    business_id: str,
    supplier_id: str,
    data: QuickSaveIn,
    user_id: str | None = None,
):
    """Create a reminder list and all of its items in ONE transaction.

    Unit defaults come from the supplier-product override, then the product's
    unit. A repeated product_id in the payload keeps only the first quantity.
    """
    _get_supplier(db, business_id, supplier_id)

    # Resolve and validate every line before writing, so a cross-supplier or
    # missing product cannot leave a partially created list behind. Python
    # dicts preserve insertion order, which gives us "first quantity wins".
    prepared: list[dict] = []
    seen: set[str] = set()
    for item in data.items:
        product_id = item.product_id
        if product_id in seen:
            continue
        product = _validate_product(db, business_id, product_id)
        link = _validate_supplier_product_link(db, business_id, supplier_id, product_id)
        seen.add(product_id)
        prepared.append(
            {
                "product": product,
                "quantity": item.quantity,
                "unit": item.unit or (link.unit if link else None) or product.unit or "pcs",
                "expected_price": item.expected_price,
                "notes": item.notes,
            }
        )

    with db.begin_nested():
        reminder_list = PurchaseReminderList(
            business_id=business_id,
            supplier_id=supplier_id,
            title=data.title,
            notes=data.notes,
            created_by=user_id,
        )
        db.add(reminder_list)
        db.flush()

        for entry in prepared:
            product = entry["product"]
            db.add(
                PurchaseReminderItem(
                    business_id=business_id,
                    list_id=reminder_list.id,
                    product_id=product.id,
                    name=product.name,
                    quantity=entry["quantity"],
                    unit=entry["unit"],
                    expected_price=entry["expected_price"],
                    notes=entry["notes"],
                    is_purchased=False,
                )
            )
        db.flush()
        audit_service.log_activity(
            db,
            business_id,
            user_id=user_id,
            action="supplier.reminder.quick_save",
            category="supplier",
            reference=data.title,
            entity_type="purchase_reminder_list",
            entity_id=reminder_list.id,
            details={"supplier_id": supplier_id, "item_count": len(prepared)},
        )

    return reminder_list_out(db, reminder_list)


# ---------------------------------------------------------------------------
# Visits
# ---------------------------------------------------------------------------
def visit_out(visit: SupplierVisit):
    from app.schemas.supplier import VisitOut

    return VisitOut.model_validate(visit)


def list_visits(db: Session, business_id: str, supplier_id: str):
    _get_supplier(db, business_id, supplier_id)
    return list(
        db.execute(
            select(SupplierVisit)
            .where(
                SupplierVisit.business_id == business_id,
                SupplierVisit.supplier_id == supplier_id,
            )
            .order_by(SupplierVisit.visit_date.desc(), SupplierVisit.id.desc())
        ).scalars().all()
    )


def create_visit(
    db: Session,
    business_id: str,
    supplier_id: str,
    data: VisitCreate,
    user_id: str | None = None,
) -> SupplierVisit:
    _get_supplier(db, business_id, supplier_id)
    payload = data.model_dump(exclude_unset=True)
    if payload.get("visit_date") is None:
        payload.pop("visit_date", None)  # let the model default to today
    visit = SupplierVisit(
        business_id=business_id, supplier_id=supplier_id, created_by=user_id, **payload
    )
    db.add(visit)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.visit.add",
        category="supplier",
        reference=str(visit.visit_date),
        entity_type="supplier_visit",
        entity_id=visit.id,
        details={"supplier_id": supplier_id},
    )
    return visit


def update_visit(
    db: Session,
    business_id: str,
    supplier_id: str,
    visit_id: str,
    data: VisitUpdate,
    user_id: str | None = None,
) -> SupplierVisit:
    visit = db.execute(
        select(SupplierVisit).where(
            SupplierVisit.id == visit_id,
            SupplierVisit.supplier_id == supplier_id,
            SupplierVisit.business_id == business_id,
        )
    ).scalars().first()
    if not visit:
        raise NotFoundError("Supplier visit not found")
    payload = data.model_dump(exclude_unset=True)
    if payload.get("visit_date") is None:
        payload.pop("visit_date", None)
    for key, value in payload.items():
        setattr(visit, key, value)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="supplier.visit.update",
        category="supplier",
        entity_type="supplier_visit",
        entity_id=visit.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return visit


# ---------------------------------------------------------------------------
# Conversion: reminder list -> purchase + REAL stock movements
# ---------------------------------------------------------------------------
def _next_purchase_number(db: Session, business_id: str) -> str:
    prefix = f"PUR-{date.today():%Y%m%d}"
    count = db.execute(
        select(func.count()).where(SupplierPurchase.business_id == business_id)
    ).scalar_one()
    candidate = f"{prefix}-{count + 1:04d}"
    while db.execute(
        select(SupplierPurchase.id).where(SupplierPurchase.purchase_number == candidate)
    ).first():
        count += 1
        candidate = f"{prefix}-{count + 1:04d}"
    return candidate


def _purchase_out(purchase: SupplierPurchase, movement_count: int) -> SupplierPurchaseOut:
    out = SupplierPurchaseOut.model_validate(purchase)
    items = purchase.__dict__.get("_converted_items", [])
    out.items = [SupplierPurchaseItemOut.model_validate(item) for item in items]
    out.stock_movements = movement_count
    return out


def convert_to_purchase(
    db: Session,
    business_id: str,
    user: User,
    list_id: str,
    data: ConvertToPurchaseIn,
) -> SupplierPurchaseOut:
    """Convert a reminder list into a purchase in a single transaction.

    Only items linked to a real BillFlow product create purchase lines and
    stock movements. Custom-name items are carried into the purchase notes.
    """
    reminder_list = _get_reminder_list(db, business_id, list_id)
    if reminder_list.status == "converted":
        raise ConflictError("This reminder list has already been converted")

    all_items = list(
        db.execute(
            select(PurchaseReminderItem)
            .where(
                PurchaseReminderItem.business_id == business_id,
                PurchaseReminderItem.list_id == list_id,
            )
            .order_by(PurchaseReminderItem.created_at.asc(), PurchaseReminderItem.id.asc())
        ).scalars().all()
    )
    selected = [i for i in all_items if i.is_purchased] if data.only_purchased else all_items
    if not selected:
        raise ValidationError("No reminder items selected for conversion")

    purchase_number = _next_purchase_number(db, business_id)
    purchase_date = data.purchase_date or date.today()
    supplier = _get_supplier(db, business_id, reminder_list.supplier_id)
    created_items: list[SupplierPurchaseItem] = []
    custom_lines: list[str] = []
    movement_count = 0

    # Everything below is one atomic unit: a failure rolls back the purchase,
    # its items, the stock changes/movements and the list status together.
    with db.begin_nested():
        purchase = SupplierPurchase(
            business_id=business_id,
            supplier_id=reminder_list.supplier_id,
            purchase_number=purchase_number,
            purchase_date=purchase_date,
            reminder_list_id=reminder_list.id,
            notes=data.notes,
            created_by=user.id,
        )
        db.add(purchase)
        db.flush()

        for item in selected:
            quantity = float(item.quantity or 0)
            unit = f" {item.unit}" if item.unit else ""
            if not item.product_id:
                custom_lines.append(
                    f"{item.name} x {quantity:g}{unit}"
                    + (
                        f" @ {_money(item.expected_price):.2f}"
                        if item.expected_price is not None
                        else ""
                    )
                )
                continue

            product = db.execute(
                select(Product).where(
                    Product.id == item.product_id, Product.business_id == business_id
                )
            ).scalars().first()
            if not product:
                # The product was removed after the reminder was written.
                custom_lines.append(f"{item.name} x {quantity:g}{unit} (product unavailable)")
                continue

            before = float(product.stock or 0)
            after = before + quantity
            product.stock = after
            inventory_service.record_movement(
                db,
                business_id=business_id,
                product=product,
                quantity_change=quantity,
                quantity_before=before,
                quantity_after=after,
                reason="purchase",
                reference=purchase_number,
                user_id=user.id,
                user_name=user.full_name,
                notes=(
                    f"Purchase {purchase_number} from {supplier.name}"
                    + (f" — reminder: {reminder_list.title}" if reminder_list.title else "")
                ),
            )
            unit_price = (
                float(item.expected_price)
                if item.expected_price is not None
                else float(product.price or 0)
            )
            purchase_item = SupplierPurchaseItem(
                business_id=business_id,
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=_money(unit_price),
                line_total=_money(quantity * unit_price),
                reminder_item_id=item.id,
            )
            db.add(purchase_item)
            created_items.append(purchase_item)
            movement_count += 1

        if custom_lines:
            extra = (
                "Custom items (carried over, not added to inventory): "
                + "; ".join(custom_lines)
            )
            existing = (purchase.notes or "").strip()
            purchase.notes = f"{existing}\n{extra}" if existing else extra

        reminder_list.status = "converted"
        db.flush()

        audit_service.log_activity(
            db,
            business_id,
            user_id=user.id,
            user_name=user.full_name,
            action="supplier.purchase.convert",
            category="supplier",
            reference=purchase_number,
            entity_type="supplier_purchase",
            entity_id=purchase.id,
            details={
                "supplier_name": supplier.name,
                "reminder_list_id": reminder_list.id,
                "item_count": len(created_items),
                "stock_movements": movement_count,
                "custom_item_count": len(custom_lines),
            },
        )
        audit_service.log_activity(
            db,
            business_id,
            user_id=user.id,
            user_name=user.full_name,
            action="supplier.reminder.convert",
            category="supplier",
            reference=reminder_list.title,
            entity_type="purchase_reminder_list",
            entity_id=reminder_list.id,
            details={"purchase_number": purchase_number},
        )

    # Stash the created lines for the output DTO without relying on a
    # relationship load after the savepoint has been released.
    purchase._converted_items = created_items
    return _purchase_out(purchase, movement_count)


def list_purchases(db: Session, business_id: str, supplier_id: str | None = None):
    stmt = select(SupplierPurchase).where(SupplierPurchase.business_id == business_id)
    if supplier_id:
        stmt = stmt.where(SupplierPurchase.supplier_id == supplier_id)
    return list(
        db.execute(stmt.order_by(SupplierPurchase.created_at.desc())).scalars().all()
    )
