"""Owner-only supplier management API."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_owner
from app.models.user import User
from app.schemas.common import MessageResponse, Paginated
from app.schemas.supplier import (
    CategoryDiscovery,
    ConvertToPurchaseIn,
    ReminderItemCreate,
    ReminderItemOut,
    ReminderItemUpdate,
    ReminderListCreate,
    ReminderListOut,
    ReminderListUpdate,
    SupplierCreate,
    SupplierDetail,
    SupplierListOut,
    SupplierProductCreate,
    SupplierProductOut,
    SupplierProductUpdate,
    SupplierPurchaseItemOut,
    SupplierPurchaseOut,
    SupplierUpdate,
    VisitCreate,
    VisitOut,
    VisitUpdate,
)
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _invalid(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Static routes FIRST so dynamic /{supplier_id} paths cannot shadow them.
# ---------------------------------------------------------------------------
@router.get("", response_model=Paginated[SupplierListOut])
def list_suppliers(
    q: str | None = None,
    category: str | None = None,
    product_type: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    items, total = supplier_service.list_suppliers(
        db,
        user.business_id,
        q=q,
        category=category,
        product_type=product_type,
        sort=sort,
        order=order,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return Paginated(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/categories", response_model=CategoryDiscovery)
def discover_categories(
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return supplier_service.discover_categories(db, user.business_id)


@router.post("", response_model=SupplierListOut, status_code=status.HTTP_201_CREATED)
def create_supplier(
    data: SupplierCreate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    supplier = supplier_service.create_supplier(db, user.business_id, data, user.id)
    supplier.product_count = 0
    return supplier


# -- reminder items / conversion -------------------------------------------
@router.get("/reminders/{list_id}/items", response_model=list[ReminderItemOut])
def list_reminder_items(
    list_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return [
            supplier_service.reminder_item_out(item)
            for item in supplier_service.list_reminder_items(
                db, user.business_id, list_id
            )
        ]
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.post(
    "/reminders/{list_id}/items",
    response_model=ReminderItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_reminder_item(
    list_id: str,
    data: ReminderItemCreate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        item = supplier_service.add_reminder_item(
            db, user.business_id, list_id, data, user.id
        )
        return supplier_service.reminder_item_out(item)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    except supplier_service.ValidationError as exc:
        raise _invalid(exc)


@router.patch("/reminders/{list_id}/items/{item_id}", response_model=ReminderItemOut)
def update_reminder_item(
    list_id: str,
    item_id: str,
    data: ReminderItemUpdate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        item = supplier_service.update_reminder_item(
            db, user.business_id, list_id, item_id, data, user.id
        )
        return supplier_service.reminder_item_out(item)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    except supplier_service.ValidationError as exc:
        raise _invalid(exc)


@router.delete("/reminders/{list_id}/items/{item_id}", response_model=MessageResponse)
def delete_reminder_item(
    list_id: str,
    item_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        supplier_service.delete_reminder_item(
            db, user.business_id, list_id, item_id, user.id
        )
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    return MessageResponse(message="Reminder item deleted")


@router.post(
    "/reminders/{list_id}/convert-to-purchase", response_model=SupplierPurchaseOut
)
def convert_to_purchase(
    list_id: str,
    data: ConvertToPurchaseIn,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return supplier_service.convert_to_purchase(
            db, user.business_id, user, list_id, data
        )
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    except supplier_service.ValidationError as exc:
        raise _invalid(exc)
    except supplier_service.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# -- supplier detail / update / deactivate ---------------------------------
@router.get("/{supplier_id}", response_model=SupplierDetail)
def get_supplier(
    supplier_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return supplier_service.get_supplier_detail(db, user.business_id, supplier_id)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.patch("/{supplier_id}", response_model=SupplierListOut)
def update_supplier(
    supplier_id: str,
    data: SupplierUpdate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        supplier = supplier_service.update_supplier(
            db, user.business_id, supplier_id, data, user.id
        )
        supplier.product_count = len(
            supplier_service.list_supplier_products(db, user.business_id, supplier_id)
        )
        return supplier
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.delete("/{supplier_id}", response_model=MessageResponse)
def deactivate_supplier(
    supplier_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        supplier_service.deactivate_supplier(db, user.business_id, supplier_id, user.id)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    return MessageResponse(message="Supplier deactivated")


# -- supplier-product links -------------------------------------------------
@router.get("/{supplier_id}/products", response_model=list[SupplierProductOut])
def list_supplier_products(
    supplier_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return [
            supplier_service.supplier_product_out(link)
            for link in supplier_service.list_supplier_products(
                db, user.business_id, supplier_id
            )
        ]
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.post(
    "/{supplier_id}/products",
    response_model=SupplierProductOut,
    status_code=status.HTTP_201_CREATED,
)
def add_supplier_product(
    supplier_id: str,
    data: SupplierProductCreate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        link = supplier_service.add_supplier_product(
            db, user.business_id, supplier_id, data, user.id
        )
        return supplier_service.supplier_product_out(link)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    except supplier_service.ValidationError as exc:
        raise _invalid(exc)


@router.patch("/{supplier_id}/products/{link_id}", response_model=SupplierProductOut)
def update_supplier_product(
    supplier_id: str,
    link_id: str,
    data: SupplierProductUpdate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        link = supplier_service.update_supplier_product(
            db, user.business_id, supplier_id, link_id, data, user.id
        )
        return supplier_service.supplier_product_out(link)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    except supplier_service.ValidationError as exc:
        raise _invalid(exc)


@router.delete("/{supplier_id}/products/{link_id}", response_model=MessageResponse)
def delete_supplier_product(
    supplier_id: str,
    link_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        supplier_service.delete_supplier_product(
            db, user.business_id, supplier_id, link_id, user.id
        )
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    return MessageResponse(message="Supplier product removed")


# -- reminder lists ---------------------------------------------------------
@router.post(
    "/{supplier_id}/reminders",
    response_model=ReminderListOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reminder_list(
    supplier_id: str,
    data: ReminderListCreate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        reminder_list = supplier_service.create_reminder_list(
            db, user.business_id, supplier_id, data, user.id
        )
        return supplier_service.reminder_list_out(db, reminder_list)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.get("/{supplier_id}/reminders", response_model=list[ReminderListOut])
def list_reminder_lists(
    supplier_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return [
            supplier_service.reminder_list_out(db, reminder_list)
            for reminder_list in supplier_service.list_reminder_lists(
                db, user.business_id, supplier_id
            )
        ]
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.patch("/reminders/{list_id}", response_model=ReminderListOut)
def update_reminder_list(
    list_id: str,
    data: ReminderListUpdate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        reminder_list = supplier_service.update_reminder_list(
            db, user.business_id, list_id, data, user.id
        )
        return supplier_service.reminder_list_out(db, reminder_list)
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
    except supplier_service.ValidationError as exc:
        raise _invalid(exc)


# -- visits -----------------------------------------------------------------
@router.get("/{supplier_id}/visits", response_model=list[VisitOut])
def list_visits(
    supplier_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return [
            supplier_service.visit_out(visit)
            for visit in supplier_service.list_visits(
                db, user.business_id, supplier_id
            )
        ]
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.post(
    "/{supplier_id}/visits",
    response_model=VisitOut,
    status_code=status.HTTP_201_CREATED,
)
def create_visit(
    supplier_id: str,
    data: VisitCreate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        return supplier_service.visit_out(
            supplier_service.create_visit(
                db, user.business_id, supplier_id, data, user.id
            )
        )
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)


@router.get("/{supplier_id}/purchases", response_model=list[SupplierPurchaseOut])
def list_purchases(
    supplier_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    from app.models.supplier import SupplierPurchaseItem

    try:
        supplier_service.get_supplier(db, user.business_id, supplier_id)
        results = []
        for purchase in supplier_service.list_purchases(db, user.business_id, supplier_id):
            items = db.execute(
                select(SupplierPurchaseItem).where(
                    SupplierPurchaseItem.purchase_id == purchase.id
                )
            ).scalars().all()
            out = SupplierPurchaseOut.model_validate(purchase)
            out.items = [SupplierPurchaseItemOut.model_validate(i) for i in items]
            results.append(out)
        return results
    except supplier_service.NotFoundError as exc:
        raise _not_found(exc)
