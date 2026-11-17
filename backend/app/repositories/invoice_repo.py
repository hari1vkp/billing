from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.product import Product
from app.repositories.base import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    model = Invoice

    def __init__(self, db: Session):
        super().__init__(db)
        self.db = db

    def next_number(self, business_id: str, prefix: str) -> str:
        """Atomically allocate the next invoice number for a business."""
        business = self.db.get(Business, business_id)
        if business is None:
            raise ValueError("Business not found")
        self.db.execute(
            select(Business.id).where(Business.id == business_id).with_for_update()
        ).scalar_one()
        self.db.refresh(business)
        business.invoice_sequence = (business.invoice_sequence or 0) + 1
        self.db.flush()
        year = date.today().year
        return f"{prefix}-{year}-{business.invoice_sequence:05d}"

    def peek_number(self, business_id: str, prefix: str) -> str:
        """Preview the next invoice number without consuming the sequence."""
        business = self.db.get(Business, business_id)
        sequence = (business.invoice_sequence or 0) if business else 0
        return f"{prefix}-{date.today().year}-{sequence + 1:05d}"

    def get_with_items(self, business_id: str, invoice_id: str) -> Invoice | None:
        stmt = (
            select(Invoice)
            .where(Invoice.business_id == business_id, Invoice.id == invoice_id)
            .options(joinedload(Invoice.items))
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_detailed(
        self,
        business_id: str,
        *,
        skip: int,
        limit: int,
        status: str | None = None,
        customer_id: str | None = None,
        query: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        stmt = (
            select(Invoice, Customer.name)
            .join(Customer, Customer.id == Invoice.customer_id)
            .where(Invoice.business_id == business_id)
        )
        if status:
            stmt = stmt.where(Invoice.status == status)
        if customer_id:
            stmt = stmt.where(Invoice.customer_id == customer_id)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                func.concat(Invoice.invoice_number, " ", func.coalesce(Customer.name, "")).ilike(like)
            )
        if date_from:
            stmt = stmt.where(Invoice.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.issue_date <= date_to)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = list(
            self.db.execute(
                stmt.order_by(Invoice.issue_date.desc(), Invoice.created_at.desc())
                .offset(skip)
                .limit(limit)
            ).all()
        )
        return rows, total

    def replace_items(self, invoice: Invoice, items: list[InvoiceItem]) -> None:
        for existing in list(invoice.items):
            self.db.delete(existing)
        self.db.flush()
        for item in items:
            item.invoice_id = invoice.id
            self.db.add(item)
        self.db.flush()
        self.db.expire(invoice, ["items"])

    def top_products(self, business_id: str, date_from, date_to, limit: int = 5):
        stmt = (
            select(
                InvoiceItem.product_id,
                func.coalesce(Product.name, InvoiceItem.description).label("name"),
                func.sum(InvoiceItem.quantity).label("qty"),
                func.sum(InvoiceItem.line_total).label("revenue"),
                func.count(func.distinct(InvoiceItem.invoice_id)).label("cnt"),
            )
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .outerjoin(Product, Product.id == InvoiceItem.product_id)
            .where(
                Invoice.business_id == business_id,
                Invoice.status != "cancelled",
            )
            .group_by(InvoiceItem.product_id, func.coalesce(Product.name, InvoiceItem.description))
            .order_by(func.sum(InvoiceItem.line_total).desc())
            .limit(limit)
        )
        if date_from:
            stmt = stmt.where(Invoice.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.issue_date <= date_to)
        return self.db.execute(stmt).all()

    def status_breakdown(self, business_id: str, date_from, date_to):
        stmt = (
            select(
                Invoice.status,
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.total_amount), 0),
            )
            .where(Invoice.business_id == business_id)
            .group_by(Invoice.status)
        )
        if date_from:
            stmt = stmt.where(Invoice.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.issue_date <= date_to)
        return self.db.execute(stmt).all()
