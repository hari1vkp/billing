"""Wholesale/retail pricing mode — authoritative, derived line pricing."""

import unittest

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register all models on the metadata
from app.core.database import Base
from app.core.migration import run_migrations
from app.models.business import Business
from app.models.product import Product
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate, InvoiceUpdate
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate
from app.services import invoice_service, product_service


class WholesalePricingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        business = Business(name="Test business", default_gst_rate=0.0)
        self.db.add(business)
        self.db.flush()
        self.business_id = business.id

        user = User(
            business_id=business.id,
            full_name="Owner",
            email="owner@test.local",
            hashed_password="hashed",
            role="owner",
        )
        self.db.add(user)
        self.db.flush()
        self.user_id = user.id
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -- helpers -----------------------------------------------------------
    def _product(self, name="Widget", price=100, discount=0, barcode=None, gst_rate=0.0):
        product = Product(
            business_id=self.business_id,
            name=name,
            price=price,
            gst_rate=gst_rate,
            stock=0,
            barcode=barcode,
            wholesale_discount_percent=discount,
        )
        self.db.add(product)
        self.db.flush()
        return product

    def _invoice(self, items, pricing_mode=None, status="unpaid", **kwargs):
        payload = dict(items=items, status=status)
        if pricing_mode is not None:
            payload["pricing_mode"] = pricing_mode
        payload.update(kwargs)
        return invoice_service.create_invoice(
            self.db, self.business_id, self.user_id, InvoiceCreate(**payload)
        )

    def _reload(self, invoice):
        self.db.expire_all()
        return invoice_service.get_invoice(self.db, self.business_id, invoice.id)

    # -- retail default ----------------------------------------------------
    def test_retail_is_default_and_uses_retail_price(self):
        product = self._product(price=100, discount=20)
        self.assertEqual(
            InvoiceCreate(items=[InvoiceItemCreate(description="x", quantity=1)]).pricing_mode,
            "retail",
        )

        invoice = self._invoice(
            [InvoiceItemCreate(product_id=product.id, quantity=2)]
        )
        self.assertEqual(invoice.pricing_mode, "retail")
        item = invoice.items[0]
        self.assertEqual(float(item.unit_price), 100.0)
        self.assertEqual(float(item.wholesale_discount_percent), 0.0)
        self.assertEqual(float(invoice.total_amount), 200.0)

    # -- wholesale derivation ----------------------------------------------
    def test_wholesale_derives_price_and_records_discount(self):
        product = self._product(price=100, discount=15)
        invoice = self._invoice(
            [
                InvoiceItemCreate(
                    product_id=product.id,
                    quantity=2,
                    unit_price=999.0,  # conflicting client price must be ignored
                )
            ],
            pricing_mode="wholesale",
        )
        self.assertEqual(invoice.pricing_mode, "wholesale")
        item = invoice.items[0]
        self.assertEqual(float(item.unit_price), 85.0)
        self.assertEqual(float(item.wholesale_discount_percent), 15.0)
        self.assertEqual(float(invoice.total_amount), 170.0)

    def test_per_product_discounts_and_zero_discount(self):
        discounted = self._product(name="A", price=100, discount=10)
        bigger = self._product(name="B", price=200, discount=25)
        no_discount = self._product(name="C", price=50, discount=0)

        invoice = self._invoice(
            [
                InvoiceItemCreate(product_id=discounted.id, quantity=1),
                InvoiceItemCreate(product_id=bigger.id, quantity=1),
                InvoiceItemCreate(product_id=no_discount.id, quantity=1),
            ],
            pricing_mode="wholesale",
        )
        self.assertEqual(
            [(float(i.unit_price), float(i.wholesale_discount_percent)) for i in invoice.items],
            [(90.0, 10.0), (150.0, 25.0), (50.0, 0.0)],
        )
        self.assertEqual(float(invoice.total_amount), 290.0)

        # The ProductOut computed field uses the same rounding rule.
        self.assertEqual(ProductOut.model_validate(discounted).wholesale_price, 90.0)
        self.assertEqual(ProductOut.model_validate(bigger).wholesale_price, 150.0)
        self.assertEqual(ProductOut.model_validate(no_discount).wholesale_price, 50.0)

    def test_rounding_of_derived_price_is_two_decimals(self):
        product = self._product(price=99.99, discount=33.33)
        invoice = self._invoice(
            [InvoiceItemCreate(product_id=product.id, quantity=1)],
            pricing_mode="wholesale",
        )
        self.assertEqual(float(invoice.items[0].unit_price), 66.66)
        self.assertEqual(ProductOut.model_validate(product).wholesale_price, 66.66)

    # -- mode switching ----------------------------------------------------
    def test_switching_mode_produces_different_totals(self):
        product = self._product(price=100, discount=10)
        items = [InvoiceItemCreate(product_id=product.id, quantity=3)]

        retail = self._invoice(items, status="draft")
        wholesale = self._invoice(items, pricing_mode="wholesale", status="draft")
        self.assertEqual(float(retail.total_amount), 300.0)
        self.assertEqual(float(wholesale.total_amount), 270.0)

    def test_draft_edit_can_switch_mode_back_and_forth(self):
        product = self._product(price=200, discount=25)
        draft = self._invoice(
            [InvoiceItemCreate(product_id=product.id, quantity=2)], status="draft"
        )
        self.assertEqual(draft.pricing_mode, "retail")
        self.assertEqual(float(draft.total_amount), 400.0)

        wholesale = invoice_service.update_invoice(
            self.db,
            self.business_id,
            draft.id,
            InvoiceUpdate(
                items=[InvoiceItemCreate(product_id=product.id, quantity=2)],
                pricing_mode="wholesale",
            ),
            user_id=self.user_id,
        )
        self.assertEqual(wholesale.pricing_mode, "wholesale")
        self.assertEqual(float(wholesale.items[0].unit_price), 150.0)
        self.assertEqual(float(wholesale.items[0].wholesale_discount_percent), 25.0)
        self.assertEqual(float(wholesale.total_amount), 300.0)

        back = invoice_service.update_invoice(
            self.db,
            self.business_id,
            draft.id,
            InvoiceUpdate(
                items=[InvoiceItemCreate(product_id=product.id, quantity=2)],
                pricing_mode="retail",
            ),
            user_id=self.user_id,
        )
        self.assertEqual(back.pricing_mode, "retail")
        self.assertEqual(float(back.items[0].unit_price), 200.0)
        self.assertEqual(float(back.items[0].wholesale_discount_percent), 0.0)
        self.assertEqual(float(back.total_amount), 400.0)

    # -- immutability of completed bills -----------------------------------
    def test_historic_invoice_unchanged_after_product_edit(self):
        product = self._product(price=100, discount=20)
        invoice = self._invoice(
            [InvoiceItemCreate(product_id=product.id, quantity=2)],
            pricing_mode="wholesale",
        )
        self.assertEqual(float(invoice.total_amount), 160.0)

        product_service.update_product(
            self.db,
            self.business_id,
            product.id,
            ProductUpdate(price=500, wholesale_discount_percent=90),
            user_id=self.user_id,
        )
        self.db.commit()

        historic = self._reload(invoice)
        self.assertEqual(float(historic.items[0].unit_price), 80.0)
        self.assertEqual(float(historic.items[0].wholesale_discount_percent), 20.0)
        self.assertEqual(float(historic.total_amount), 160.0)

    # -- edges and validation ----------------------------------------------
    def test_hundred_percent_discount(self):
        product = self._product(price=100, discount=100)
        invoice = self._invoice(
            [InvoiceItemCreate(product_id=product.id, quantity=5)],
            pricing_mode="wholesale",
        )
        self.assertEqual(float(invoice.items[0].unit_price), 0.0)
        self.assertEqual(float(invoice.items[0].wholesale_discount_percent), 100.0)
        self.assertEqual(float(invoice.total_amount), 0.0)
        self.assertEqual(ProductOut.model_validate(product).wholesale_price, 0.0)

    def test_validation_rejects_discount_over_100_and_bad_mode(self):
        with self.assertRaises(PydanticValidationError):
            ProductCreate(name="x", price=10, wholesale_discount_percent=101)
        with self.assertRaises(PydanticValidationError):
            ProductCreate(name="x", price=10, wholesale_discount_percent=-1)
        with self.assertRaises(PydanticValidationError):
            ProductUpdate(wholesale_discount_percent=100.01)
        with self.assertRaises(PydanticValidationError):
            InvoiceCreate(items=[], pricing_mode="wholesale!")
        with self.assertRaises(PydanticValidationError):
            InvoiceUpdate(pricing_mode="other")

        # 100 is the inclusive upper bound.
        self.assertEqual(
            ProductCreate(name="x", price=10, wholesale_discount_percent=100).wholesale_discount_percent,
            100.0,
        )

    def test_non_product_line_keeps_supplied_price_in_both_modes(self):
        for mode in ("retail", "wholesale"):
            invoice = self._invoice(
                [
                    InvoiceItemCreate(
                        description="Custom work",
                        quantity=2,
                        unit_price=55.5,
                    )
                ],
                pricing_mode=mode,
            )
            item = invoice.items[0]
            self.assertEqual(float(item.unit_price), 55.5)
            self.assertEqual(float(item.wholesale_discount_percent), 0.0)
            self.assertEqual(float(invoice.total_amount), 111.0)

    def test_barcode_item_uses_mode_derived_price(self):
        self._product(name="Scanned", price=100, discount=10, barcode="BC-1")
        invoice = self._invoice(
            [InvoiceItemCreate(barcode="BC-1", quantity=1)],
            pricing_mode="wholesale",
        )
        item = invoice.items[0]
        self.assertEqual(float(item.unit_price), 90.0)
        self.assertEqual(float(item.wholesale_discount_percent), 10.0)


class WholesaleMigrationTests(unittest.TestCase):
    def test_migration_adds_new_columns_idempotently(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE products ("
                    "id VARCHAR(36) PRIMARY KEY, name VARCHAR(200), "
                    "price NUMERIC(14,2), barcode VARCHAR(64), "
                    "discount_type VARCHAR(16), discount_value NUMERIC(14,2))"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE invoices ("
                    "id VARCHAR(36) PRIMARY KEY, invoice_number VARCHAR(50), "
                    "transaction_ref VARCHAR(100))"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE invoice_items ("
                    "id VARCHAR(36) PRIMARY KEY, invoice_id VARCHAR(36), "
                    "unit_price NUMERIC(14,2))"
                )
            )
            conn.execute(text("INSERT INTO products (id, name, price) VALUES ('p', 'Legacy', 100)"))
            conn.execute(text("INSERT INTO invoices (id, invoice_number) VALUES ('i', 'INV-1')"))
            conn.execute(text("INSERT INTO invoice_items (id, invoice_id, unit_price) VALUES ('ii', 'i', 100)"))

        run_migrations(engine)
        run_migrations(engine)  # idempotent

        inspector = inspect(engine)
        products = {c["name"] for c in inspector.get_columns("products")}
        invoices = {c["name"] for c in inspector.get_columns("invoices")}
        items = {c["name"] for c in inspector.get_columns("invoice_items")}
        self.assertIn("wholesale_discount_percent", products)
        self.assertIn("pricing_mode", invoices)
        self.assertIn("wholesale_discount_percent", items)

        with engine.connect() as conn:
            self.assertEqual(
                conn.execute(text("SELECT wholesale_discount_percent FROM products")).scalar_one(),
                0,
            )
            self.assertEqual(
                conn.execute(text("SELECT pricing_mode FROM invoices")).scalar_one(),
                "retail",
            )
            self.assertEqual(
                conn.execute(
                    text("SELECT wholesale_discount_percent FROM invoice_items")
                ).scalar_one(),
                0,
            )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
