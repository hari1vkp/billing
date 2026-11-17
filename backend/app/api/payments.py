from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import Paginated
from app.schemas.payment import ConfirmPaymentRequest, PaymentCreate, PaymentOut
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["Payments & Transactions"])


@router.get("", response_model=Paginated[PaymentOut])
def list_payments(
    query: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    method: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = payment_service.list_payments(
        db,
        user.business_id,
        skip=(page - 1) * page_size,
        limit=page_size,
        status=status_filter,
        method=method,
        query=query,
        date_from=from_date,
        date_to=to_date,
    )
    items = []
    for payment, invoice_number, customer_name in rows:
        item = PaymentOut.model_validate(payment)
        item.invoice_number = invoice_number
        item.customer_name = customer_name
        items.append(item)
    return Paginated(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(
    data: PaymentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return payment_service.record_payment(db, user.business_id, user.id, data)
    except payment_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (payment_service.PaymentError, payment_service.ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{payment_id}/confirm", response_model=PaymentOut)
def confirm_payment(
    payment_id: str,
    data: ConfirmPaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return payment_service.confirm_payment(db, user.business_id, payment_id, user.id, data)
    except payment_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except payment_service.PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{payment_id}/fail", response_model=PaymentOut)
def fail_payment(
    payment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return payment_service.fail_payment(db, user.business_id, payment_id)
    except payment_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{payment_id}/refund", response_model=PaymentOut)
def refund_payment(
    payment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return payment_service.refund_payment(db, user.business_id, payment_id, user.id)
    except (payment_service.NotFoundError, payment_service.PaymentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
