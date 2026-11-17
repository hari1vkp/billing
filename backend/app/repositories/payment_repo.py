from datetime import date

from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment, WebhookEvent
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    def __init__(self, db: Session):
        super().__init__(db)
        self.db = db

    def list_detailed(
        self,
        business_id: str,
        *,
        skip: int,
        limit: int,
        status: str | None = None,
        method: str | None = None,
        query: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        stmt = (
            select(Payment, Invoice.invoice_number, Customer.name)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .join(Customer, Customer.id == Payment.customer_id)
            .where(Payment.business_id == business_id)
        )
        if status:
            stmt = stmt.where(Payment.status == status)
        if method:
            stmt = stmt.where(Payment.method == method)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                func.concat(
                    func.coalesce(Payment.reference, ""),
                    " ",
                    Invoice.invoice_number,
                    " ",
                    func.coalesce(Customer.name, ""),
                ).ilike(like)
            )
        if date_from:
            stmt = stmt.where(func.coalesce(Payment.payment_date, func.cast(Payment.created_at, Date)) >= date_from)
        if date_to:
            stmt = stmt.where(func.coalesce(Payment.payment_date, func.cast(Payment.created_at, Date)) <= date_to)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = list(
            self.db.execute(
                stmt.order_by(Payment.created_at.desc()).offset(skip).limit(limit)
            ).all()
        )
        return rows, total

    def get_by_reference(self, business_id: str, reference: str) -> Payment | None:
        return self.db.execute(
            select(Payment).where(
                Payment.business_id == business_id,
                Payment.reference == reference,
            )
        ).scalar_one_or_none()

    def get_webhook_event(self, provider: str, event_id: str) -> WebhookEvent | None:
        return self.db.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == provider, WebhookEvent.event_id == event_id
            )
        ).scalar_one_or_none()

    def add_webhook_event(self, event: WebhookEvent) -> WebhookEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def method_breakdown(self, business_id: str, date_from, date_to):
        stmt = (
            select(
                Payment.method,
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
            )
            .where(Payment.business_id == business_id, Payment.status == "confirmed")
            .group_by(Payment.method)
            .order_by(func.sum(Payment.amount).desc())
        )
        if date_from:
            stmt = stmt.where(func.coalesce(Payment.payment_date, func.cast(Payment.created_at, Date)) >= date_from)
        if date_to:
            stmt = stmt.where(func.coalesce(Payment.payment_date, func.cast(Payment.created_at, Date)) <= date_to)
        return self.db.execute(stmt).all()
