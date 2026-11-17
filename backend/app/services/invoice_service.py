"""Invoice creation/editing and the amount calculation engine."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import generate_public_invoice_token
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.product import Product
from app.repositories.invoice_repo import InvoiceRepository
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate, InvoiceUpdate
from app.services import audit_service


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def money(value) -> float:
    """Round to 2 decimals using banker-safe half-up rounding."""
    return float(
        Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _build_items(db, business_id, item_dtos: list[InvoiceItemCreate]) -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    for idx, dto in enumerate(item_dtos):
        product = None
        if dto.product_id:
            product = db.query(Product).filter(
                Product.id == dto.product_id, Product.business_id == business_id
            ).first()
            if not product:
                raise ValidationError(f"Product {dto.product_id} not found")
        elif dto.barcode:
            # POS scanners send the barcode instead of an internal product id.
            barcode = str(dto.barcode).strip()
            product = db.execute(
                select(Product).where(
                    Product.business_id == business_id, Product.barcode == barcode
                )
            ).scalars().first()
            if not product:
                raise ValidationError(f"No product found for barcode '{barcode}'")

        description = dto.description or (product.name if product else "Item")
        unit_price = dto.unit_price
        if unit_price is None:
            unit_price = float(product.price) if product else 0.0
        gst_rate = dto.gst_rate
        if gst_rate is None:
            gst_rate = float(product.gst_rate) if product else 0.0

        base = money(Decimal(str(dto.quantity)) * Decimal(str(unit_price)))
        discount = money(Decimal(str(base)) * Decimal(str(dto.discount_percent)) / 100)
        taxable = money(Decimal(str(base)) - Decimal(str(discount)))
        tax = money(Decimal(str(taxable)) * Decimal(str(gst_rate)) / 100)
        line_total = money(Decimal(str(taxable)) + Decimal(str(tax)))

        items.append(
            InvoiceItem(
                product_id=product.id if product else None,
                description=description,
                quantity=dto.quantity,
                unit_price=money(unit_price),
                discount_percent=dto.discount_percent,
                discount_amount=discount,
                taxable_amount=taxable,
                gst_rate=gst_rate,
                tax_amount=tax,
                line_total=line_total,
                sort_order=idx,
            )
        )
    return items


def recalculate(invoice: Invoice) -> None:
    """Recompute all invoice totals from its line items."""
    discount_percent = invoice.discount_percent or 0
    items = list(invoice.items or [])
    subtotal = money(sum(Decimal(str(i.taxable_amount)) + Decimal(str(i.discount_amount)) for i in items))
    item_discount = money(sum(Decimal(str(i.discount_amount)) for i in items))
    taxable = money(sum(Decimal(str(i.taxable_amount)) for i in items))
    tax = money(sum(Decimal(str(i.tax_amount)) for i in items))
    after_tax = money(Decimal(str(taxable)) + Decimal(str(tax)))
    inv_discount = money(Decimal(str(after_tax)) * Decimal(str(discount_percent)) / 100)
    total = money(Decimal(str(after_tax)) - Decimal(str(inv_discount)))

    invoice.subtotal = subtotal
    invoice.discount_amount = money(Decimal(str(item_discount)) + Decimal(str(inv_discount)))
    invoice.taxable_amount = taxable
    invoice.tax_amount = tax
    invoice.total_amount = total
    invoice.balance_amount = money(Decimal(str(total)) - Decimal(str(invoice.paid_amount)))
    recompute_status(invoice)


def recompute_status(invoice: Invoice) -> None:
    if invoice.status == "cancelled":
        return
    paid = Decimal(str(invoice.paid_amount or 0))
    total = Decimal(str(invoice.total_amount or 0))
    if paid <= 0:
        invoice.status = "draft" if invoice.status == "draft" else "unpaid"
    elif paid >= total:
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"


WALK_IN_CUSTOMER = "Walk-in Customer"


def _resolve_customer(db: Session, business_id: str, customer_id: str | None) -> str:
    """Use the given customer, or get/create a fast-checkout walk-in customer."""
    if customer_id and str(customer_id).strip():
        # Verify the customer belongs to this business.
        customer = db.execute(
            select(Customer.id).where(
                Customer.id == customer_id, Customer.business_id == business_id
            )
        ).first()
        if not customer:
            raise ValidationError(f"Customer {customer_id} not found")
        return customer_id

    customer = db.execute(
        select(Customer)
        .where(
            Customer.business_id == business_id,
            Customer.name == WALK_IN_CUSTOMER,
            Customer.is_active.is_(True),
        )
        .order_by(Customer.created_at)
    ).scalars().first()
    if not customer:
        customer = Customer(
            business_id=business_id, name=WALK_IN_CUSTOMER, phone=None, email=None
        )
        db.add(customer)
        db.flush()
    return customer.id


def create_invoice(db: Session, business_id: str, user_id: str, data: InvoiceCreate) -> Invoice:
    from app.models.business import Business

    business = db.get(Business, business_id)
    if not business:
        raise NotFoundError("Business not found")

    customer_id = _resolve_customer(db, business_id, data.customer_id)
    repo = InvoiceRepository(db)
    issue_date = data.issue_date or date.today()
    # Default payment terms: 15 days.
    due_date = data.due_date or issue_date + timedelta(days=15)
    invoice_number = repo.next_number(business_id, business.invoice_prefix)

    invoice = Invoice(
        business_id=business_id,
        customer_id=customer_id,
        invoice_number=invoice_number,
        transaction_ref=invoice_number,
        issue_date=issue_date,
        due_date=due_date,
        status=data.status,
        discount_percent=data.discount_percent,
        notes=data.notes,
        public_token=generate_public_invoice_token(),
        created_by=user_id,
        paid_amount=0,
    )
    db.add(invoice)
    db.flush()

    for item in _build_items(db, business_id, data.items):
        item.invoice_id = invoice.id
        db.add(item)
    db.flush()
    db.refresh(invoice, ["items"])

    recalculate(invoice)
    db.flush()

    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="invoice.create",
        category="invoice",
        reference=invoice_number,
        entity_type="invoice",
        entity_id=invoice.id,
        details={
            "total_amount": float(invoice.total_amount),
            "item_count": len(invoice.items),
            "customer_id": customer_id,
        },
    )
    return repo.get_with_items(business_id, invoice.id)


def update_invoice(
    db: Session,
    business_id: str,
    invoice_id: str,
    data: InvoiceUpdate,
    user_id: str | None = None,
) -> Invoice:
    repo = InvoiceRepository(db)
    invoice = repo.get_with_items(business_id, invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")
    if invoice.status == "cancelled":
        raise ValidationError("Cancelled invoices cannot be edited")

    payload = data.model_dump(exclude_unset=True)
    items_dto = payload.pop("items", None)

    for key, value in payload.items():
        setattr(invoice, key, value)

    if items_dto is not None:
        new_items = _build_items(db, business_id, items_dto)
        repo.replace_items(invoice, new_items)
        db.refresh(invoice, ["items"])

    recalculate(invoice)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="invoice.update",
        category="invoice",
        reference=invoice.invoice_number,
        entity_type="invoice",
        entity_id=invoice.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return repo.get_with_items(business_id, invoice_id)


def set_status(
    db: Session,
    business_id: str,
    invoice_id: str,
    status: str,
    user_id: str | None = None,
) -> Invoice:
    repo = InvoiceRepository(db)
    invoice = repo.get_with_items(business_id, invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")
    if status == "cancelled":
        invoice.status = "cancelled"
        invoice.cancelled_at = datetime.now(timezone.utc)
    else:
        invoice.status = status
        recompute_status(invoice)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="invoice.cancel" if status == "cancelled" else "invoice.status",
        category="invoice",
        reference=invoice.invoice_number,
        entity_type="invoice",
        entity_id=invoice.id,
        details={"status": invoice.status},
    )
    return repo.get_with_items(business_id, invoice_id)


def get_invoice(db: Session, business_id: str, invoice_id: str) -> Invoice:
    invoice = InvoiceRepository(db).get_with_items(business_id, invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")
    return invoice


def get_by_public_token(db: Session, token: str) -> Invoice | None:
    return db.query(Invoice).filter(Invoice.public_token == token).first()


def list_invoices(db, business_id, **kwargs):
    return InvoiceRepository(db).list_detailed(business_id, **kwargs)
