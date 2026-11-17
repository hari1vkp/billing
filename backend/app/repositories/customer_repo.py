from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerInteraction
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    def __init__(self, db: Session):
        super().__init__(db)
        self.db = db

    def search(self, business_id: str, query: str | None, skip: int, limit: int):
        stmt = select(Customer).where(Customer.business_id == business_id)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                func.concat(Customer.name, " ", func.coalesce(Customer.phone, ""), " ",
                            func.coalesce(Customer.email, "")).ilike(like)
            )
        total = self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        items = list(
            self.db.execute(
                stmt.order_by(Customer.created_at.desc()).offset(skip).limit(limit)
            ).scalars().all()
        )
        return items, total

    def stats(self, business_id: str, customer_id: str) -> dict:
        inv = self.db.execute(
            select(
                func.coalesce(func.sum(Invoice.total_amount), 0),
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.balance_amount), 0),
                func.max(Invoice.issue_date),
            ).where(
                Invoice.business_id == business_id,
                Invoice.customer_id == customer_id,
                Invoice.status != "cancelled",
            )
        ).one()
        paid = self.db.execute(
            select(
                func.coalesce(func.sum(Payment.amount), 0),
                func.max(Payment.payment_date),
            ).where(
                Payment.business_id == business_id,
                Payment.customer_id == customer_id,
                Payment.status == "confirmed",
            )
        ).one()
        return {
            "total_purchases": float(inv[0] or 0),
            "invoice_count": int(inv[1] or 0),
            "outstanding_balance": float(inv[2] or 0),
            "last_invoice_date": inv[3],
            "total_paid": float(paid[0] or 0),
            "last_transaction_date": paid[1],
        }

    def interactions(self, business_id: str, customer_id: str, limit: int = 50):
        return list(
            self.db.execute(
                select(CustomerInteraction)
                .where(
                    CustomerInteraction.business_id == business_id,
                    CustomerInteraction.customer_id == customer_id,
                )
                .order_by(CustomerInteraction.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def add_interaction(self, interaction: CustomerInteraction) -> CustomerInteraction:
        self.db.add(interaction)
        self.db.flush()
        return interaction
