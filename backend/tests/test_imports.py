"""Lightweight unit tests for product import, AI prompts and barcode labels."""

import unittest

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register all models on the metadata
from app.core.database import Base
from app.core.migration import run_migrations
from app.models.activity_log import ActivityLog
from app.models.business import Business
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.services import ai_catalogue_service, import_service, product_service
from app.schemas.product import ProductOut

EXACT_HEADER = (
    "Product Name,Brand,Category,Subcategory,Variant,Size / Pack Size,Barcode,"
    "Barcode Type,SKU,Purchase Price,Selling Price,Discount Type,Discount Value,"
    "Opening Stock"
)


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
        lines = import_service.template_csv().decode("utf-8").strip().splitlines()
        self.assertEqual(lines[0], EXACT_HEADER)
        self.assertEqual(len(lines), 5)  # header + 2 instructions + 2 examples
        self.assertTrue(lines[1].startswith("#"))
        self.assertTrue(lines[2].startswith("#"))
        self.assertIn("8901234567890", lines[3])  # manufacturer example
        self.assertEqual(lines[4].split(",")[6], "")  # internal example: blank barcode
        self.assertEqual(lines[4].split(",")[7], "internal")

    # -- AI prompt ---------------------------------------------------------
    def test_ai_prompt_is_long_tailored_and_contains_exact_header(self):
        categories = ai_catalogue_service.CATEGORIES
        self.assertEqual(
            [c["id"] for c in categories],
            [
                "grocery", "general", "clothing", "mobile", "electronics",
                "footwear", "cosmetics", "pharmacy", "other",
            ],
        )
        for category in categories:
            self.assertEqual(
                set(category), {"id", "label", "description"}
            )
            prompt = ai_catalogue_service.generate_prompt(
                category["id"], business_name="Test Kirana", extra_notes="Festive season"
            )
            self.assertGreater(len(prompt), 1000)
            self.assertIn(EXACT_HEADER, prompt)
            self.assertIn("150-300", prompt)
            self.assertIn("not a short sample", prompt)
            self.assertIn("Test Kirana", prompt)
            self.assertIn("Festive season", prompt)

        grocery = ai_catalogue_service.generate_prompt("grocery")
        self.assertIn("pulses", grocery)
        clothing = ai_catalogue_service.generate_prompt("clothing")
        self.assertIn("sizes", clothing)
        self.assertIn("colours", clothing)
        self.assertIn("Indian brands", clothing)

    # -- parsing -----------------------------------------------------------
    def test_column_alias_mapping_and_validation(self):
        csv_text = (
            "Product Name,EAN,Cost Price,Rate,Qty,Group,GST %\n"
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
        recognized = preview["recognized_columns"]
        self.assertEqual(recognized["name"], "Product Name")
        self.assertEqual(recognized["barcode"], "EAN")
        self.assertEqual(recognized["cost_price"], "Cost Price")
        self.assertEqual(recognized["selling_price"], "Rate")
        self.assertEqual(recognized["quantity"], "Qty")
        self.assertEqual(recognized["category"], "Group")
        self.assertEqual(recognized["gst_rate"], "GST %")
        for key in (
            "brand", "subcategory", "variant", "size_pack", "barcode_type",
            "sku", "discount_type", "discount_value",
        ):
            self.assertIsNone(recognized[key])
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
        self.assertEqual(good["discount_type"], "none")
        self.assertEqual(good["discount_value"], 0.0)

        self.assertIn("Selling price is required", preview["rows"][1]["errors"])
        self.assertIn("Quantity cannot be negative", preview["rows"][2]["errors"])
        self.assertIn("GST rate must be between 0 and 100", preview["rows"][2]["errors"])

    def test_official_template_parses_with_all_new_fields(self):
        preview = import_service.parse_file(
            "template.csv", import_service.template_csv()
        )
        self.assertEqual(preview["total_rows"], 2)
        self.assertEqual(preview["error_count"], 0)
        first, second = preview["rows"]
        self.assertEqual(first["brand"], "Amul")
        self.assertEqual(first["subcategory"], "Butter")
        self.assertEqual(first["variant"], "Unsalted")
        self.assertEqual(first["size_pack"], "500 g")
        self.assertEqual(first["barcode_type"], "manufacturer")
        self.assertEqual(first["sku"], "AMUL-BTR-500")
        self.assertEqual(first["discount_type"], "none")
        self.assertEqual(second["name"], "Cotton T-Shirt")
        self.assertIsNone(second["barcode"])
        self.assertEqual(second["barcode_type"], "internal")
        self.assertEqual(second["discount_type"], "percent")
        self.assertEqual(second["discount_value"], 10.0)

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
        self.assertTrue(any("Duplicate barcode" in e for e in preview["rows"][2]["errors"]))

    def test_discount_validation(self):
        csv_text = (
            "name,selling_price,discount type,discount value\n"
            "A,100,percent,10\n"
            "B,100,percent,150\n"
            "C,100,flat,500\n"
            "D,100,flat,-1\n"
            "E,100,something,5\n"
        )
        preview = import_service.parse_file("products.csv", csv_text.encode("utf-8"))
        rows = preview["rows"]
        self.assertTrue(rows[0]["valid"])
        self.assertEqual(rows[0]["discount_value"], 10.0)
        self.assertIn("cannot exceed 100", rows[1]["errors"][0])
        self.assertTrue(rows[2]["valid"])
        self.assertIn("cannot be negative", rows[3]["errors"][0])
        self.assertIn("one of: none, percent, flat", rows[4]["errors"][0])

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
        self.assertIn("Category: Tools", product.description)
        self.assertIn("Barcode Type: manufacturer", product.description)
        self.assertEqual(product.discount_type, "none")
        self.assertEqual(float(product.discount_value), 0.0)
        self.assertTrue(product.track_inventory)
        self.assertFalse(product.is_service)
        self.assertEqual(
            ProductOut.model_validate(product).discount_type, "none"
        )

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
        actions = {row[0] for row in self.db.execute(select(ActivityLog.action))}
        self.assertIn("product.update", actions)

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

    # -- barcode rules -----------------------------------------------------
    def test_internal_barcode_and_sku_are_generated_and_scannable(self):
        summary = import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [{"name": "Unknown Barcode Item", "selling_price": 50, "quantity": 4}],
        )
        self.db.commit()
        self.assertEqual(summary["created"], 1)
        product = self.db.execute(select(Product)).scalars().one()
        self.assertRegex(product.barcode, r"^BF\d{10}$")
        self.assertTrue(product.sku.startswith("SKU-BF"))
        self.assertIn("Barcode Type: internal", product.description)
        # Generated codes must work with the existing POS barcode lookup.
        found = product_service.get_by_barcode(
            self.db, self.business_id, product.barcode
        )
        self.assertEqual(found.id, product.id)

    def test_manufacturer_barcode_is_preserved_exactly(self):
        import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [
                {
                    "name": "Branded Item",
                    "barcode": "8901234567890",
                    "barcode_type": "manufacturer",
                    "selling_price": 99,
                    "discount_type": "percent",
                    "discount_value": 5,
                }
            ],
        )
        self.db.commit()
        product = self.db.execute(select(Product)).scalars().one()
        self.assertEqual(product.barcode, "8901234567890")
        self.assertEqual(product.sku, "8901234567890")
        self.assertEqual(product.discount_type, "percent")
        self.assertEqual(float(product.discount_value), 5.0)

    def test_duplicate_barcode_in_commit_is_skipped(self):
        rows = [
            {"name": "First", "barcode": "999", "selling_price": 10},
            {"name": "Second", "barcode": "999", "selling_price": 20},
        ]
        summary = import_service.commit_rows(
            self.db, self.business_id, self.user_id, rows
        )
        self.db.commit()
        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertTrue(
            any("Duplicate barcode" in err["message"] for err in summary["errors"])
        )

    def test_variant_rows_get_unique_skus_and_decorated_names(self):
        rows = [
            {
                "name": "Cotton T-Shirt",
                "category": "Clothing",
                "variant": "Red",
                "size_pack": "M",
                "selling_price": 599,
            },
            {
                "name": "Cotton T-Shirt",
                "category": "Clothing",
                "variant": "Blue",
                "size_pack": "L",
                "selling_price": 599,
            },
        ]
        summary = import_service.commit_rows(
            self.db, self.business_id, self.user_id, rows
        )
        self.db.commit()
        self.assertEqual(summary["created"], 2)
        products = list(
            self.db.execute(select(Product).order_by(Product.name)).scalars().all()
        )
        self.assertEqual(
            [p.name for p in products],
            ["Cotton T-Shirt — Blue / L", "Cotton T-Shirt — Red / M"],
        )
        self.assertEqual(len({p.sku for p in products}), 2)
        self.assertEqual(len({p.barcode for p in products}), 2)
        self.assertTrue(all(p.description and "Variant:" in p.description for p in products))

    # -- labels / migration ------------------------------------------------
    def test_label_pdf_magic_bytes(self):
        import_service.commit_rows(
            self.db,
            self.business_id,
            self.user_id,
            [{"name": "Label Item", "selling_price": 10, "quantity": 1}],
        )
        self.db.commit()
        product = self.db.execute(select(Product)).scalars().one()
        pdf = import_service.barcode_labels_pdf([product])
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 500)

    def test_migration_adds_discount_columns_to_legacy_table(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE products ("
                    "id VARCHAR(36) PRIMARY KEY, business_id VARCHAR(36) NOT NULL, "
                    "name VARCHAR(200) NOT NULL, sku VARCHAR(50), barcode VARCHAR(64), "
                    "description TEXT, hsn_code VARCHAR(20), price NUMERIC(14,2) NOT NULL, "
                    "gst_rate NUMERIC(5,2) NOT NULL, stock NUMERIC(14,3) NOT NULL, "
                    "track_inventory BOOLEAN NOT NULL, is_service BOOLEAN NOT NULL, "
                    "low_stock_threshold NUMERIC(14,3) NOT NULL, is_active BOOLEAN NOT NULL, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
                )
            )
        run_migrations(engine)
        columns = {c["name"] for c in inspect(engine).get_columns("products")}
        self.assertIn("discount_type", columns)
        self.assertIn("discount_value", columns)
        # Idempotent: running twice must not fail or add duplicate columns.
        run_migrations(engine)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
