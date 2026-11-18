"""Lightweight unit tests for the product-import service (SQLite in-memory)."""

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register all models on the metadata
from app.core.database import Base
from app.models.activity_log import ActivityLog
from app.models.business import Business
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.services import import_service


class ImportServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        business = Business(name="Test business", default_gst_rate=12.0)
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

    # -- template ----------------------------------------------------------
    def test_template_csv(self):
        text = import_service.template_csv().decode("utf-8")
        lines = text.strip().splitlines()
        self.assertEqual(
            lines[0], "name,barcode,cost_price,selling_price,quantity,category,gst_rate"
        )
        self.assertTrue(lines[1].startswith("#"))

    # -- parsing -----------------------------------------------------------
    def test_column_alias_mapping_and_validation(self):
        csv_text = (
            "Product Name,EAN,Cost Price,Rate,Qty,Brand,GST %\n"
            "Widget,123456,40,100,5,Tools,12\n"
            "No Price,999,10,,0,,18\n"
            "Negative Stock,888,10,50,-2,,200\n"
            "#Example row,777,1,2,3,X,18\n"
        )
        preview = import_service.parse_file(
            "products.csv",
            csv_text.encode("utf-8"),
            default_gst_rate=18.0,
            db=self.db,
            business_id=self.business_id,
        )
        self.assertEqual(
            preview["recognized_columns"],
            {
                "name": "Product Name",
                "barcode": "EAN",
                "cost_price": "Cost Price",
                "selling_price": "Rate",
                "quantity": "Qty",
                "category": "Brand",
                "gst_rate": "GST %",
            },
        )
        self.assertEqual(preview["unsupported_columns"], [])
        self.assertEqual(preview["total_rows"], 3)
        self.assertEqual(preview["error_count"], 2)

        good = preview["rows"][0]
        self.assertTrue(good["valid"])
        self.assertEqual(good["name"], "Widget")
        self.assertEqual(good["barcode"], "123456")
        self.assertEqual(good["cost_price"], 40.0)
        self.assertEqual(good["selling_price"], 100.0)
        self.assertEqual(good["quantity"], 5.0)
        self.assertEqual(good["category"], "Tools")
        self.assertEqual(good["gst_rate"], 12.0)

        self.assertIn("Selling price is required", preview["rows"][1]["errors"])
        self.assertIn("Quantity cannot be negative", preview["rows"][2]["errors"])
        self.assertIn("GST rate must be between 0 and 100", preview["rows"][2]["errors"])

    def test_gst_defaults_from_business_when_blank(self):
        csv_text = "name,selling_price\nWidget,100\n"
        preview = import_service.parse_file(
            "products.csv", csv_text.encode("utf-8"), default_gst_rate=12.0
        )
        self.assertEqual(preview["rows"][0]["gst_rate"], 12.0)
        self.assertIsNone(preview["rows"][0]["barcode"])
        self.assertIsNone(preview["rows"][0]["cost_price"])

    def test_duplicate_and_existing_barcode_warnings(self):
        import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [{"name": "Existing", "barcode": "111", "selling_price": 50, "quantity": 2}],
        )
        self.db.commit()
        csv_text = (
            "name,barcode,selling_price,quantity\n"
            "A,111,10,1\n"
            "B,222,20,2\n"
            "C,222,30,3\n"
        )
        preview = import_service.parse_file(
            "products.csv",
            csv_text.encode("utf-8"),
            default_gst_rate=18.0,
            db=self.db,
            business_id=self.business_id,
        )
        self.assertTrue(any("already belongs" in w for w in preview["rows"][0]["warnings"]))
        self.assertTrue(any("Duplicate barcode" in w for w in preview["rows"][2]["warnings"]))

    # -- commit ------------------------------------------------------------
    def _new_row(self, name="Widget", barcode="123", quantity=10, price=100):
        return {
            "name": name,
            "barcode": barcode,
            "cost_price": 60,
            "selling_price": price,
            "quantity": quantity,
            "category": "Tools",
            "gst_rate": 12,
        }

    def test_commit_creates_product_with_opening_stock(self):
        summary = import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [self._new_row()],
        )
        self.db.commit()
        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["stock_movements"], 1)
        self.assertGreaterEqual(summary["activity_entries"], 2)

        product = self.db.execute(
            select(Product).where(Product.barcode == "123")
        ).scalars().one()
        self.assertEqual(float(product.stock), 10.0)
        self.assertEqual(product.sku, "123")
        self.assertEqual(product.description, "Tools")
        self.assertTrue(product.track_inventory)
        self.assertFalse(product.is_service)

        movement = self.db.execute(select(StockMovement)).scalars().one()
        self.assertEqual(movement.reason, "opening_stock")
        self.assertEqual(float(movement.quantity_before), 0.0)
        self.assertEqual(float(movement.quantity_after), 10.0)

        actions = {row[0] for row in self.db.execute(select(ActivityLog.action))}
        self.assertIn("product.create", actions)
        self.assertIn("product.import", actions)

    def test_commit_no_overwrite_default(self):
        import_service.commit_rows(
            self.db, self.business_id, self.user_id, [self._new_row(quantity=10)]
        )
        self.db.commit()
        summary = import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [self._new_row(quantity=99)],
            overwrite_stock=False,
        )
        self.db.commit()
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["stock_movements"], 0)

        product = self.db.execute(
            select(Product).where(Product.barcode == "123")
        ).scalars().one()
        self.assertEqual(float(product.stock), 10.0)
        movements = self.db.execute(
            select(StockMovement).where(StockMovement.reason == "correction")
        ).scalars().all()
        self.assertEqual(movements, [])

    def test_commit_overwrite_records_correction(self):
        import_service.commit_rows(
            self.db, self.business_id, self.user_id, [self._new_row(quantity=10)]
        )
        self.db.commit()
        summary = import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [self._new_row(quantity=99)],
            overwrite_stock=True,
        )
        self.db.commit()
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["stock_movements"], 1)

        product = self.db.execute(
            select(Product).where(Product.barcode == "123")
        ).scalars().one()
        self.assertEqual(float(product.stock), 99.0)
        movement = self.db.execute(
            select(StockMovement).where(StockMovement.reason == "correction")
        ).scalars().one()
        self.assertEqual(float(movement.quantity_before), 10.0)
        self.assertEqual(float(movement.quantity_after), 99.0)

    def test_commit_skips_invalid_rows(self):
        summary = import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [
                {"name": "", "selling_price": 10, "quantity": 1},
                {"name": "Bad", "selling_price": -5, "quantity": 1},
                {"name": "Good", "selling_price": 10, "quantity": 0},
            ],
        )
        self.db.commit()
        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["skipped"], 2)
        self.assertEqual(len(summary["errors"]), 2)

    def test_commit_ambiguous_name_match_is_skipped(self):
        for barcode in ("a", "b"):
            self.db.add(
                Product(
                    business_id=self.business_id,
                    name="Duplicate",
                    barcode=barcode,
                    price=10,
                    stock=0,
                )
            )
        self.db.commit()
        summary = import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [{"name": "Duplicate", "selling_price": 10, "quantity": 3}],
        )
        self.assertEqual(summary["skipped"], 1)
        self.assertTrue(summary["errors"])
        self.assertIn("Ambiguous", summary["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
