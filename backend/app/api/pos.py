"""Cashier checkout endpoints — deliberately small and focused."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.pos import (
    PosCheckoutRequest,
    PosCheckoutResponse,
    PosQRResponse,
    PosQuoteRequest,
)
from app.services import invoice_service, payment_service, pos_service

router = APIRouter(prefix="/pos", tags=["POS Checkout"])


@router.get("/next-number")
def next_invoice_number(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"invoice_number": pos_service.preview_invoice_number(db, user.business_id)}


@router.post("/qr", response_model=PosQRResponse)
def checkout_qr(
    data: PosQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return pos_service.build_qr(db, user.business_id, data)
    except pos_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except invoice_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/checkout", response_model=PosCheckoutResponse)
def complete_checkout(
    data: PosCheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return pos_service.complete_checkout(db, user.business_id, user.id, data)
    except (
        pos_service.ValidationError,
        invoice_service.ValidationError,
        invoice_service.NotFoundError,
        payment_service.PaymentError,
        payment_service.ValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
