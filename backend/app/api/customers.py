from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse, Paginated
from app.schemas.customer import (
    CustomerCreate,
    CustomerDetail,
    CustomerOut,
    CustomerUpdate,
    InteractionCreate,
    InteractionOut,
)
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["Customers (CRM)"])


@router.get("", response_model=Paginated[CustomerOut])
def list_customers(
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = customer_service.list_customers(
        db, user.business_id, query, (page - 1) * page_size, page_size
    )
    return Paginated(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(
    customer_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return customer_service.get_customer_detail(db, user.business_id, customer_id)
    except customer_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    data: CustomerCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return customer_service.create_customer(db, user.business_id, data, user.id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    data: CustomerUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return customer_service.update_customer(db, user.business_id, customer_id, data, user.id)
    except customer_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{customer_id}", response_model=MessageResponse)
def delete_customer(
    customer_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        customer_service.delete_customer(db, user.business_id, customer_id, user.id)
    except customer_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except customer_service.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return MessageResponse(message="Customer deleted")


@router.post(
    "/{customer_id}/interactions",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_interaction(
    customer_id: str,
    data: InteractionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return customer_service.add_interaction(
            db, user.business_id, customer_id, user.id, data
        )
    except customer_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
