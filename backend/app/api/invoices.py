import base64
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.common import Paginated
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceListItem,
    InvoiceOut,
    InvoiceUpdate,
    StatusUpdate,
)
from app.schemas.payment import PaymentOut
from app.services import invoice_service, payment_service, pdf_service, upi_service

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _enrich(db: Session, invoice: Invoice) -> InvoiceOut:
    out = InvoiceOut.model_validate(invoice)
    customer = db.get(Customer, invoice.customer_id)
    if customer:
        out.customer_name = customer.name
        out.customer_phone = customer.phone
        out.customer_email = customer.email
    return out


@router.get("", response_model=Paginated[InvoiceListItem])
def list_invoices(
    query: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    customer_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = invoice_service.list_invoices(
        db,
        user.business_id,
        skip=(page - 1) * page_size,
        limit=page_size,
        status=status_filter,
        customer_id=customer_id,
        query=query,
        date_from=from_date,
        date_to=to_date,
    )
    items = []
    for invoice, customer_name in rows:
        item = InvoiceListItem.model_validate(invoice)
        item.customer_name = customer_name
        items.append(item)
    return Paginated(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _enrich(db, invoice_service.get_invoice(db, user.business_id, invoice_id))
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    data: InvoiceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _enrich(db, invoice_service.create_invoice(db, user.business_id, user.id, data))
    except (invoice_service.NotFoundError, invoice_service.ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: str,
    data: InvoiceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _enrich(
            db, invoice_service.update_invoice(db, user.business_id, invoice_id, data, user.id)
        )
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except invoice_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{invoice_id}/status", response_model=InvoiceOut)
def update_status(
    invoice_id: str,
    data: StatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _enrich(
            db, invoice_service.set_status(db, user.business_id, invoice_id, data.status, user.id)
        )
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except invoice_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{invoice_id}/payments", response_model=list[PaymentOut])
def list_invoice_payments(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Payments for an invoice, for POS receipt/polling (any authenticated role)."""
    try:
        invoice = invoice_service.get_invoice(db, user.business_id, invoice_id)
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    rows = payment_service.get_payments_for_invoice(db, user.business_id, invoice_id)
    customer = db.get(Customer, invoice.customer_id)
    result = []
    for payment in rows:
        item = PaymentOut.model_validate(payment)
        item.invoice_number = invoice.invoice_number
        item.customer_name = customer.name if customer else None
        result.append(item)
    return result


@router.get("/{invoice_id}/pdf")
def download_pdf(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        invoice = invoice_service.get_invoice(db, user.business_id, invoice_id)
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    business = db.get(Business, user.business_id)
    customer = db.get(Customer, invoice.customer_id)
    payments = payment_service.get_payments_for_invoice(db, user.business_id, invoice_id)
    pdf = pdf_service.generate_invoice_pdf(invoice, business, customer, payments)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'
        },
    )


@router.get("/{invoice_id}/qr")
def invoice_qr(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        invoice = invoice_service.get_invoice(db, user.business_id, invoice_id)
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    business = db.get(Business, user.business_id)
    if not business.upi_id:
        raise HTTPException(status_code=400, detail="UPI ID is not configured in business settings")
    uri = upi_service.invoice_upi_uri(business, invoice)
    png = upi_service.generate_qr_png(uri)
    return {
        "upi_uri": uri,
        "qr_data_url": "data:image/png;base64," + base64.b64encode(png).decode(),
        "amount": float(invoice.balance_amount or invoice.total_amount),
        "upi_id": business.upi_id,
        "payee_name": business.upi_name or business.name,
        "invoice_number": invoice.invoice_number,
        "transaction_ref": invoice.transaction_ref or invoice.invoice_number,
    }


@router.get("/{invoice_id}/qr.png")
def invoice_qr_png(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        invoice = invoice_service.get_invoice(db, user.business_id, invoice_id)
    except invoice_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    business = db.get(Business, user.business_id)
    if not business.upi_id:
        raise HTTPException(status_code=400, detail="UPI ID is not configured")
    png = upi_service.generate_qr_png(upi_service.invoice_upi_uri(business, invoice))
    return Response(content=png, media_type="image/png")
