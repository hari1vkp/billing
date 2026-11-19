"""Tests for the standalone Barcode Sticker Studio backend."""

import re
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register all models on the metadata
from app.core.database import Base, get_db
from app.core.deps import require_owner
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.business import Business
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.services import barcode_sticker_service as stickers


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


def _page_sizes(pdf: bytes) -> list[tuple[float, float]]:
    return [
        (float(width), float(height))
        for width, height in re.findall(
            rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", pdf
        )
    ]


def _pdf_text(pdf: bytes) -> str | None:
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=pdf,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:  # pragma: no cover - optional system binary
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


class BarcodeStickerServiceTests(unittest.TestCase):
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
            email="owner@stickers.test.local",
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

    def _product(
        self, name, barcode=None, sku=None, price=123.45, stock=12.5, business_id=None
    ):
        product = Product(
            business_id=business_id or self.business_id,
            name=name,
            barcode=barcode,
            sku=sku,
            price=price,
            stock=stock,
        )
        self.db.add(product)
        self.db.flush()
        return product

    # -- ensure -------------------------------------------------------------
    def test_existing_barcodes_are_reused_exactly(self):
        branded = self._product("Branded", barcode="8901234567890", sku="BRAND")
        internal = self._product("Internal", barcode="BF0000000042", sku="SKU-BF42")
        blank = self._product("Blank", barcode=None, sku="BLANK")

        mapping, generated = stickers.ensure_barcodes(
            self.db,
            self.business_id,
            [branded.id, internal.id, blank.id],
            self.user_id,
        )
        self.assertEqual(mapping[branded.id], "8901234567890")
        self.assertEqual(mapping[internal.id], "BF0000000042")
        self.assertRegex(mapping[blank.id], r"^BF\d{10}$")
        self.assertEqual(generated, [blank.id])
        self.assertEqual(len(set(mapping.values())), 3)

        # Idempotent: a second pass never regenerates an existing code.
        again, generated_again = stickers.ensure_barcodes(
            self.db,
            self.business_id,
            [branded.id, internal.id, blank.id],
            self.user_id,
        )
        self.assertEqual(again, mapping)
        self.assertEqual(generated_again, [])

        actions = {row[0] for row in self.db.execute(select(ActivityLog.action))}
        self.assertIn("product.update", actions)
        updates = self.db.execute(
            select(ActivityLog).where(ActivityLog.action == "product.update")
        ).scalars().all()
        self.assertEqual(len(updates), 1)  # only the blank product was written
        self.assertEqual(updates[0].entity_id, blank.id)

    def test_generated_barcodes_are_unique_and_tenant_scoped(self):
        own = self._product("Own", barcode="BF1111111111")
        other_business = Business(name="Other", default_gst_rate=18.0)
        self.db.add(other_business)
        self.db.flush()
        self._product("Other tenant", barcode="BF2222222222", business_id=other_business.id)
        blank = self._product("Blank", barcode=None)

        # First candidate collides with our tenant (skipped); the second is
        # used by another tenant only, so it is free for this tenant.
        def fake_randbelow(_):
            return candidates.pop(0)

        candidates = [1111111111, 2222222222]
        with mock.patch.object(
            stickers.secrets, "randbelow", side_effect=fake_randbelow
        ):
            mapping, generated = stickers.ensure_barcodes(
                self.db, self.business_id, [own.id, blank.id], self.user_id
            )
        self.assertEqual(generated, [blank.id])
        self.assertEqual(mapping[blank.id], "BF2222222222")
        self.assertNotEqual(mapping[blank.id], mapping[own.id])
        self.assertEqual(candidates, [])

    def test_stock_price_sku_and_barcode_source_never_change(self):
        product = self._product(
            "Untouched", barcode=None, sku="KEEP-SKU", price=999.99, stock=44.25
        )
        before = (float(product.price), float(product.stock), product.sku)
        mapping, generated = stickers.ensure_barcodes(
            self.db, self.business_id, [product.id], self.user_id
        )
        self.assertEqual(generated, [product.id])
        self.assertEqual(float(product.price), before[0])
        self.assertEqual(float(product.stock), before[1])
        self.assertEqual(product.sku, before[2])
        self.assertEqual(product.barcode, mapping[product.id])
        self.assertEqual(
            self.db.execute(select(StockMovement)).scalars().all(), []
        )

    def test_missing_product_raises_not_found(self):
        with self.assertRaises(stickers.NotFoundError):
            stickers.ensure_barcodes(self.db, self.business_id, ["no-such-id"])

    # -- preview ------------------------------------------------------------
    def test_preview_svg_contains_real_barcode_and_metadata(self):
        product = self._product("Amul Butter", barcode="8901234567890", sku="AMUL")
        preview = stickers.build_preview(
            self.db,
            self.business_id,
            [{"product_id": product.id, "quantity": 3}],
        )
        self.assertIn("<svg", preview["svg"][:400])
        self.assertIn("8901234567890", preview["svg"])
        self.assertIn("Amul Butter", preview["svg"])
        # The bars are real vector shapes, not just the human-readable number.
        self.assertGreater(preview["svg"].count("<rect"), 20)
        self.assertEqual(preview["total_stickers"], 3)
        self.assertEqual(preview["pages"], 1)
        self.assertEqual((preview["width_mm"], preview["height_mm"]), (40.0, 25.0))
        self.assertEqual(preview["layout"], "sheet")
        self.assertEqual(
            preview["items"],
            [{
                "product_id": product.id,
                "name": "Amul Butter",
                "barcode": "8901234567890",
                "quantity": 3,
            }],
        )
        self.assertTrue(stickers._valid_ean13("8901234567890"))
        self.assertFalse(stickers._valid_ean13("8901234567891"))
        self.assertFalse(stickers._valid_ean13("BF0000000042"))

    def test_preview_ensures_missing_barcodes_before_rendering(self):
        product = self._product("No code yet", barcode=None)
        preview = stickers.build_preview(
            self.db,
            self.business_id,
            [{"product_id": product.id, "quantity": 1}],
        )
        barcode = preview["items"][0]["barcode"]
        self.assertRegex(barcode, r"^BF\d{10}$")
        self.assertIn(barcode, preview["svg"])

    # -- PDF ----------------------------------------------------------------
    def test_sheet_pdf_has_exact_sticker_occurrences(self):
        products = [
            self._product("Alpha", barcode="111111111111"),
            self._product("Beta", barcode="222222222222"),
            self._product("Gamma", barcode="333333333333"),
        ]
        items = [
            {"product_id": products[0].id, "quantity": 10},
            {"product_id": products[1].id, "quantity": 5},
            {"product_id": products[2].id, "quantity": 20},
        ]
        pdf = stickers.build_pdf(self.db, self.business_id, items)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(_page_count(pdf), 1)  # small stickers: 4 x 10 = 40/page
        text = _pdf_text(pdf)
        self.assertIsNotNone(text)
        for barcode, quantity in (("111111111111", 10), ("222222222222", 5), ("333333333333", 20)):
            self.assertEqual(text.count(barcode), quantity)
        self.assertEqual(sum(text.count(b) for b in ("111111111111", "222222222222", "333333333333")), 35)

    def test_sheet_pdf_continues_on_more_pages(self):
        product = self._product("Many", barcode="BF0000000099")
        pdf = stickers.build_pdf(
            self.db,
            self.business_id,
            [{"product_id": product.id, "quantity": 45}],
        )
        self.assertEqual(_page_count(pdf), 2)
        text = _pdf_text(pdf)
        self.assertIsNotNone(text)
        self.assertEqual(text.count("BF0000000099"), 45)
        preview = stickers.build_preview(
            self.db,
            self.business_id,
            [{"product_id": product.id, "quantity": 45}],
        )
        self.assertEqual(preview["pages"], 2)

    def test_individual_pdf_uses_actual_page_size_and_one_per_page(self):
        product = self._product("Custom", barcode="8901234567890")
        pdf = stickers.build_pdf(
            self.db,
            self.business_id,
            [{"product_id": product.id, "quantity": 3}],
            size="custom",
            width_mm=55.5,
            height_mm=30.5,
            layout="individual",
        )
        expected_w = float(stickers._decimal(55.5, "w") * stickers.MM_TO_PT)
        expected_h = float(stickers._decimal(30.5, "h") * stickers.MM_TO_PT)
        sizes = _page_sizes(pdf)
        self.assertEqual(len(sizes), 3)
        for width, height in sizes:
            self.assertAlmostEqual(width, expected_w, places=2)
            self.assertAlmostEqual(height, expected_h, places=2)
        text = _pdf_text(pdf)
        self.assertIsNotNone(text)
        self.assertEqual(text.count("8901234567890"), 3)

    def test_pdf_sizes_and_custom_validation(self):
        product = self._product("Sized", barcode="BF0000000007")
        for size, width, height in (
            ("small", 40.0, 25.0),
            ("medium", 50.0, 30.0),
            ("large", 60.0, 40.0),
            ("xl", 100.0, 50.0),
        ):
            preview = stickers.build_preview(
                self.db,
                self.business_id,
                [{"product_id": product.id, "quantity": 1}],
                size=size,
            )
            self.assertEqual((preview["width_mm"], preview["height_mm"]), (width, height))
        for width, height in ((0, 25), (-1, 25), (301, 25), (40, 400)):
            with self.assertRaises(stickers.ValidationError):
                stickers.build_preview(
                    self.db,
                    self.business_id,
                    [{"product_id": product.id, "quantity": 1}],
                    size="custom",
                    width_mm=width,
                    height_mm=height,
                )
        with self.assertRaises(stickers.ValidationError):
            stickers.build_preview(
                self.db,
                self.business_id,
                [{"product_id": product.id, "quantity": 1}],
                size="custom",
            )

    # -- validation ---------------------------------------------------------
    def test_quantity_and_layout_validation(self):
        product = self._product("Validated", barcode="BF0000000011")
        for quantity in (0, -2, 1.5):
            with self.assertRaises(stickers.ValidationError):
                stickers.build_pdf(
                    self.db,
                    self.business_id,
                    [{"product_id": product.id, "quantity": quantity}],
                )
        with self.assertRaises(stickers.ValidationError):
            stickers.build_pdf(
                self.db,
                self.business_id,
                [{"product_id": product.id, "quantity": 5001}],
            )
        with self.assertRaises(stickers.ValidationError):
            stickers.build_preview(
                self.db,
                self.business_id,
                [{"product_id": product.id, "quantity": 1}],
                layout="unknown",
            )
        with self.assertRaises(stickers.ValidationError):
            stickers.build_preview(self.db, self.business_id, [])


class BarcodeStickerApiTests(unittest.TestCase):
    def setUp(self):
        # TestClient runs endpoints in a worker thread.
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        business = Business(name="API business", default_gst_rate=18.0)
        self.db.add(business)
        self.db.flush()
        self.business_id = business.id
        user = User(
            business_id=business.id,
            full_name="Owner",
            email="api-owner@stickers.test.local",
            hashed_password="hashed",
            role="owner",
        )
        self.db.add(user)
        self.db.flush()
        self.db.commit()
        self.product = Product(
            business_id=business.id,
            name="API Product",
            barcode=None,
            sku="API-SKU",
            price=50,
            stock=8,
        )
        self.db.add(self.product)
        self.db.flush()
        self.db.commit()

        owner_id, business_id = str(user.id), str(business.id)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[require_owner] = lambda: SimpleNamespace(
            id=owner_id, business_id=business_id, role="owner"
        )
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_endpoints_and_error_mapping(self):
        url = "/api/v1/barcode-stickers"
        ensured = self.client.post(url + "/ensure", json={"product_ids": [self.product.id]})
        self.assertEqual(ensured.status_code, 200)
        payload = ensured.json()
        barcode = payload["barcodes"][self.product.id]
        self.assertRegex(barcode, r"^BF\d{10}$")
        self.assertEqual(payload["generated"], [self.product.id])

        preview = self.client.post(
            url + "/preview",
            json={"items": [{"product_id": self.product.id, "quantity": 2}]},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn(barcode, preview.json()["svg"])
        self.assertEqual(preview.json()["total_stickers"], 2)

        pdf = self.client.post(
            url + "/pdf",
            json={"items": [{"product_id": self.product.id, "quantity": 2}]},
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertEqual(
            pdf.headers["content-disposition"],
            'inline; filename="billflow-barcode-stickers.pdf"',
        )
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        bad = self.client.post(
            url + "/preview",
            json={"items": [{"product_id": self.product.id, "quantity": 0}]},
        )
        self.assertEqual(bad.status_code, 400)
        missing = self.client.post(
            url + "/preview",
            json={"items": [{"product_id": "missing", "quantity": 1}]},
        )
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
