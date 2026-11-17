from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse, Paginated
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Products & Inventory"])


@router.get("", response_model=Paginated[ProductOut])
def list_products(
    query: str | None = None,
    low_stock_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = product_service.list_products(
        db, user.business_id, query, low_stock_only, (page - 1) * page_size, page_size
    )
    return Paginated(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_product_by_barcode(
    barcode: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """POS barcode lookup — any authenticated role, scoped to the tenant."""
    try:
        return product_service.get_by_barcode(db, user.business_id, barcode)
    except product_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return product_service.get_product(db, user.business_id, product_id)
    except product_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return product_service.create_product(db, user.business_id, data, user.id)
    except product_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    data: ProductUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return product_service.update_product(db, user.business_id, product_id, data, user.id)
    except product_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except product_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{product_id}", response_model=MessageResponse)
def delete_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        product_service.delete_product(db, user.business_id, product_id, user.id)
    except product_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MessageResponse(message="Product archived")
