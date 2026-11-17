"""Seed realistic demo data into the database.

Usage:  .venv/bin/python seed.py
All analytics in the app are computed from these *real* persisted records.
"""

import random
from datetime import date, timedelta

from app.core.database import Base, SessionLocal, engine
import app.models  # noqa: F401  (register models)
from app.core.security import hash_password
from app.models.business import Business
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User
from app.schemas.customer import CustomerCreate, InteractionCreate
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.schemas.payment import PaymentCreate
from app.schemas.product import ProductCreate
from app.services import (
    customer_service,
    invoice_service,
    payment_service,
    product_service,
)

random.seed(42)


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Business).count():
            print("Database already contains data; skipping seed.")
            return

        business = Business(
            name="Shree Ganesh Traders",
            legal_name="Shree Ganesh Traders Pvt Ltd",
            email="hello@shreeganeshtraders.in",
            phone="+91 98200 11223",
            address="12, Sitabuldi Main Road",
            city="Nagpur",
            state="Maharashtra",
            pincode="440012",
            gstin="27AABCS1234M1ZP",
            upi_id="shreeganesh@okhdfcbank",
            upi_name="Shree Ganesh Traders",
            invoice_prefix="SGT",
            invoice_footer="Thank you for shopping with us. Goods once sold will not be taken back.",
        )
        db.add(business)
        db.flush()

        owner = User(
            business_id=business.id,
            full_name="Amit Sharma",
            email="demo@billingapp.com",
            phone="+91 98200 11223",
            hashed_password=hash_password("Demo@1234"),
            role="owner",
        )
        staff = User(
            business_id=business.id,
            full_name="Priya Nair",
            email="staff@billingapp.com",
            phone="+91 98200 44556",
            hashed_password=hash_password("Staff@1234"),
            role="staff",
        )
        db.add_all([owner, staff])
        db.flush()

        products_data = [
            ("Cotton T-Shirt", "TSH-001", 349, 5, 220, False),
            ("Denim Jeans", "DNM-014", 899, 5, 165, False),
            ("Leather Wallet", "WLT-007", 599, 12, 108, False),
            ("Sports Shoes", "SHO-022", 1299, 12, 134, False),
            ("Wrist Watch", "WCH-003", 1899, 18, 105, False),
            ("Sunglasses", "SUN-011", 749, 12, 122, False),
            ("Gift Wrapping Service", "SRV-001", 99, 18, 0, True),
            ("Home Delivery Service", "SRV-002", 49, 18, 0, True),
        ]
        products = []
        for name, sku, price, gst, stock, is_service in products_data:
            p = product_service.create_product(
                db,
                business.id,
                ProductCreate(
                    name=name,
                    sku=sku,
                    price=price,
                    gst_rate=gst,
                    stock=stock,
                    is_service=is_service,
                    track_inventory=not is_service,
                    low_stock_threshold=15,
                    hsn_code="6109" if not is_service else "9987",
                ),
            )
            products.append(p)

        customers_data = [
            ("Rahul Verma", "+91 98765 43210", "rahul.verma@example.com", "Nagpur"),
            ("Sneha Kulkarni", "+91 98765 11122", "sneha.k@example.com", "Pune"),
            ("Arjun Mehta", "+91 99876 54321", "arjun.mehta@example.com", "Mumbai"),
            ("Priya Desai", "+91 91234 56789", "priya.desai@example.com", "Nagpur"),
            ("Vikram Singh", "+91 90000 12345", "vikram.s@example.com", "Indore"),
            ("Ananya Rao", "+91 90123 45678", "ananya.rao@example.com", "Bangalore"),
            ("Karan Patel", "+91 93265 47891", "karan.patel@example.com", "Ahmedabad"),
            ("Meera Iyer", "+91 94012 34567", "meera.iyer@example.com", "Chennai"),
        ]
        customers = []
        for name, phone, email, city in customers_data:
            c = customer_service.create_customer(
                db,
                business.id,
                CustomerCreate(name=name, phone=phone, email=email, city=city,
                               state="Maharashtra", address=f"{name.split()[0]} Residence, {city}"),
            )
            customers.append(c)

        # One deliberately low-stock item to demonstrate alerts.
        products[2].stock = 25

        # Interaction history for a couple of customers
        customer_service.add_interaction(
            db, business.id, customers[0].id, owner.id,
            InteractionCreate(
                type="call", content="Discussed bulk order for the festive season."
            ),
        )
        customer_service.add_interaction(
            db, business.id, customers[2].id, owner.id,
            InteractionCreate(
                type="note", content="Prefers UPI payments. Repeat customer since 2024."
            ),
        )

        today = date.today()
        statuses = ["paid"] * 14 + ["partially_paid"] * 4 + ["unpaid"] * 4 + ["cancelled"] * 2
        random.shuffle(statuses)

        for i, status in enumerate(statuses):
            customer = customers[i % len(customers)]
            days_ago = random.randint(0, 170)
            issue = today - timedelta(days=days_ago)
            n_items = random.randint(1, 3)
            chosen = random.sample(products, n_items)
            items = [
                InvoiceItemCreate(
                    product_id=p.id,
                    quantity=random.randint(1, 4),
                    discount_percent=random.choice([0, 0, 5, 10]),
                )
                for p in chosen
            ]
            invoice = invoice_service.create_invoice(
                db,
                business.id,
                owner.id,
                InvoiceCreate(customer_id=customer.id, issue_date=issue, items=items,
                              discount_percent=random.choice([0, 0, 0, 2])),
            )

            if status in ("paid", "partially_paid"):
                amount = float(invoice.total_amount) if status == "paid" else round(
                    float(invoice.total_amount) * 0.4, 2
                )
                payment = payment_service.record_payment(
                    db,
                    business.id,
                    owner.id,
                    PaymentCreate(
                        invoice_id=invoice.id,
                        amount=amount,
                        method=random.choice(["upi", "upi", "upi", "cash", "card"]),
                        reference=f"UTR{random.randint(10**9, 10**10 - 1)}",
                        payment_date=issue + timedelta(days=random.randint(0, 3)),
                        confirm=True,
                    ),
                )
                if status == "paid":
                    payment.payment_date = issue + timedelta(days=random.randint(0, 3))
                    db.flush()

            if status == "cancelled":
                invoice_service.set_status(db, business.id, invoice.id, "cancelled")

        # A pending payment awaiting staff confirmation (demonstrates workflow)
        pending_invoice = invoice_service.create_invoice(
            db,
            business.id,
            owner.id,
            InvoiceCreate(
                customer_id=customers[1].id,
                issue_date=today,
                items=[InvoiceItemCreate(product_id=products[3].id, quantity=1)],
            ),
        )
        payment_service.record_payment(
            db,
            business.id,
            owner.id,
            PaymentCreate(
                invoice_id=pending_invoice.id,
                amount=float(pending_invoice.total_amount),
                method="upi",
                payment_date=today,
                confirm=False,
            ),
        )

        db.commit()
        print(
            f"Seeded business '{business.name}' with {len(customers)} customers, "
            f"{len(products)} products, {len(statuses) + 1} invoices."
        )
        print("Login: demo@billingapp.com / Demo@1234")
    finally:
        db.close()


if __name__ == "__main__":
    main()
