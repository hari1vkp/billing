"""Supplier-specific product cards and purchase reminders — contract tests."""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all models on the metadata
from app.api import suppliers as suppliers_api
from app.core.database import Base, get_db
from app.core.deps import get_current_user, require_owner
from app.core.migration import run_migrations
from app.models.business import Business
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.supplier import (
    PurchaseReminderItem,
    PurchaseReminderList,
    Supplier,
    SupplierProduct,
    SupplierPurchase,
)
from app.models.user import User


class SupplierReminderApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        business = Business(name="Reminder business", default_gst_rate=0.0)
        self.db.add(business)
        self.db.flush()
        self.business_id = business.id

        self.owner = User(
            business_id=business.id,
            full_name="Owner",
            email="owner@reminder.local",
            hashed_password="x",
            role="owner",
        )
        self.db.add(self.owner)
        self.db.flush()
        self.db.commit()

        self.app = FastAPI()
        self.app.include_router(suppliers_api.router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[require_owner] = lambda: self.owner
        # get_current_user is overridden too so the staff-forbidden path stays sane.
        self.app.dependency_overrides[get_current_user] = lambda: self.owner
        self.client = TestClient(self.app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -- helpers -----------------------------------------------------------
    def _supplier(self, name):
        response = self.client.post("/api/v1/suppliers", json={"name": name})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _product(self, name, *, unit="pcs", description=None, stock=0, price=10):
        product = Product(
            business_id=self.business_id,
            name=name,
            price=price,
            stock=stock,
            gst_rate=0,
            unit=unit,
            description=description,
        )
        self.db.add(product)
        self.db.flush()
        return product

    def _link(self, supplier_id, product_id, *, unit=None, price=None):
        payload = {"product_id": product_id}
        if unit is not None:
            payload["unit"] = unit
        if price is not None:
            payload["supplier_price"] = price
        response = self.client.post(
            f"/api/v1/suppliers/{supplier_id}/products", json=payload
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _list(self, supplier_id, title="Visit"):
        response = self.client.post(
            f"/api/v1/suppliers/{supplier_id}/reminders", json={"title": title}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _item(self, list_id, *, name="Item", product_id=None, quantity=1, unit=None):
        payload = {"name": name, "quantity": quantity}
        if product_id is not None:
            payload["product_id"] = product_id
        if unit is not None:
            payload["unit"] = unit
        return self.client.post(
            f"/api/v1/suppliers/reminders/{list_id}/items", json=payload
        )

    # -- 1. supplier-linked product cards -----------------------------------
    def test_only_supplier_linked_products_returned_with_display_metadata(self):
        supplier_a = self._supplier("Supplier A")
        supplier_b = self._supplier("Supplier B")

        p1 = self._product(
            "Milk 1L",
            unit="L",
            description="Brand: Acme | Category: Dairy | Variant: Toned | Size: 1L",
        )
        p2 = self._product("Only at B", unit="box")
        p3 = self._product("Rice", unit="kg")
        p4 = self._product(
            "JSON product",
            unit="pcs",
            description=(
                '{"brand": "JsonBrand", "category": "Grains", '
                '"variant": "Basmati", "size_pack": "5 kg"}'
            ),
        )
        p5 = self._product("Plain product", unit="pcs", description="Just some prose")

        self._link(supplier_a, p1.id)
        self._link(supplier_b, p2.id)
        self._link(supplier_a, p3.id, unit="500 g")
        self._link(supplier_a, p4.id)
        self._link(supplier_a, p5.id)

        response = self.client.get(f"/api/v1/suppliers/{supplier_a}/products")
        self.assertEqual(response.status_code, 200, response.text)
        cards = {row["product_id"]: row for row in response.json()}

        # Never leak a product linked only to another supplier.
        self.assertNotIn(p2.id, cards)
        self.assertEqual(set(cards), {p1.id, p3.id, p4.id, p5.id})

        milk = cards[p1.id]
        self.assertEqual(milk["product_name"], "Milk 1L")
        self.assertEqual(milk["product_brand"], "Acme")
        self.assertEqual(milk["product_category"], "Dairy")
        self.assertEqual(milk["product_variant"], "Toned")
        self.assertEqual(milk["product_size_pack"], "1L")
        self.assertEqual(milk["product_unit"], "L")
        self.assertEqual(milk["unit"], "L")  # no supplier override -> product unit

        rice = cards[p3.id]
        self.assertEqual(rice["product_unit"], "kg")
        self.assertEqual(rice["unit"], "500 g")  # supplier override wins

        json_card = cards[p4.id]
        self.assertEqual(json_card["product_brand"], "JsonBrand")
        self.assertEqual(json_card["product_category"], "Grains")
        self.assertEqual(json_card["product_variant"], "Basmati")
        self.assertEqual(json_card["product_size_pack"], "5 kg")

        plain = cards[p5.id]
        for field in (
            "product_brand",
            "product_category",
            "product_variant",
            "product_size_pack",
        ):
            self.assertIsNone(plain[field], "metadata must never be invented")

    # -- 2. relationship validation ----------------------------------------
    def test_cross_supplier_product_rejected_on_add_update_and_quick_save(self):
        supplier_a = self._supplier("Supplier A")
        supplier_b = self._supplier("Supplier B")
        product_at_b = self._product("B-only product")
        shared = self._product("Shared product")
        self._link(supplier_b, product_at_b.id)
        self._link(supplier_b, shared.id)
        self._link(supplier_a, shared.id)

        list_a = self._list(supplier_a, "A visit")

        # add: product offered only by another supplier -> 422
        rejected = self._item(list_a, product_id=product_at_b.id, quantity=1)
        self.assertEqual(rejected.status_code, 422, rejected.text)

        # a product linked to several suppliers is fine for either one
        accepted = self._item(list_a, product_id=shared.id, quantity=1)
        self.assertEqual(accepted.status_code, 201, accepted.text)
        item_id = accepted.json()["id"]

        # update: repointing an item at a cross-supplier product -> 422
        rejected_update = self.client.patch(
            f"/api/v1/suppliers/reminders/{list_a}/items/{item_id}",
            json={"product_id": product_at_b.id},
        )
        self.assertEqual(rejected_update.status_code, 422, rejected_update.text)
        self.assertEqual(self.db.get(PurchaseReminderItem, item_id).product_id, shared.id)

        # quick-save: bad relationship rolls the whole payload back
        lists_before = self.db.execute(
            select(func.count()).select_from(PurchaseReminderList)
        ).scalar_one()
        bad_save = self.client.post(
            f"/api/v1/suppliers/{supplier_a}/reminders/quick-save",
            json={
                "title": "Should not exist",
                "items": [
                    {"product_id": shared.id, "quantity": 1},
                    {"product_id": product_at_b.id, "quantity": 2},
                ],
            },
        )
        self.assertEqual(bad_save.status_code, 422, bad_save.text)
        self.assertEqual(
            self.db.execute(
                select(func.count()).select_from(PurchaseReminderList)
            ).scalar_one(),
            lists_before,
        )
        self.assertEqual(
            self.db.execute(
                select(func.count()).select_from(PurchaseReminderItem)
            ).scalar_one(),
            1,
        )

    # -- 3. duplicate prevention -------------------------------------------
    def test_duplicate_item_returns_existing_item_unchanged(self):
        supplier = self._supplier("Dup Vendor")
        product = self._product("Biscuits", unit="pack")
        self._link(supplier, product.id)
        reminder_list = self._list(supplier)

        first = self._item(
            reminder_list, name="First", product_id=product.id, quantity=3, unit="packs"
        )
        self.assertEqual(first.status_code, 201, first.text)
        original = first.json()

        duplicate = self._item(
            reminder_list, name="Different", product_id=product.id, quantity=99, unit="boxes"
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(duplicate.json()["id"], original["id"])
        self.assertEqual(float(duplicate.json()["quantity"]), 3.0)
        self.assertEqual(duplicate.json()["unit"], "packs")
        self.assertEqual(duplicate.json()["name"], "First")

        self.assertEqual(
            self.db.execute(
                select(func.count())
                .select_from(PurchaseReminderItem)
                .where(PurchaseReminderItem.list_id == reminder_list)
            ).scalar_one(),
            1,
        )

    # -- 4. quick-save ------------------------------------------------------
    def test_quick_save_defaults_units_and_dedupes_payload(self):
        supplier = self._supplier("Quick Vendor")
        p_kg = self._product("Atta", unit="kg")
        p_box = self._product("Soap", unit="box")
        p_custom = self._product("Oil", unit="L")
        self._link(supplier, p_kg.id)
        self._link(supplier, p_box.id, unit="500 g")
        self._link(supplier, p_custom.id)

        response = self.client.post(
            f"/api/v1/suppliers/{supplier}/reminders/quick-save",
            json={
                "title": "  Weekly restock  ",
                "notes": "gate note",
                "items": [
                    {"product_id": p_kg.id, "quantity": 2},
                    {"product_id": p_box.id, "quantity": 5},
                    {"product_id": p_custom.id, "quantity": 1, "unit": "bottle"},
                    {"product_id": p_kg.id, "quantity": 99, "unit": "wrong"},
                ],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["title"], "Weekly restock")
        self.assertEqual(body["notes"], "gate note")
        self.assertEqual(body["supplier_id"], supplier)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(len(body["items"]), 3)

        by_product = {i["product_id"]: i for i in body["items"]}
        self.assertEqual(float(by_product[p_kg.id]["quantity"]), 2.0)  # first wins
        self.assertEqual(by_product[p_kg.id]["unit"], "kg")  # product default
        self.assertEqual(float(by_product[p_box.id]["quantity"]), 5.0)
        self.assertEqual(by_product[p_box.id]["unit"], "500 g")  # supplier override
        self.assertEqual(by_product[p_custom.id]["unit"], "bottle")  # explicit wins
        self.assertEqual(by_product[p_kg.id]["name"], "Atta")

        # Everything landed in one list, in the database, too.
        self.assertEqual(
            self.db.execute(
                select(func.count()).select_from(PurchaseReminderItem)
            ).scalar_one(),
            3,
        )

    def test_quick_save_is_transactional(self):
        supplier = self._supplier("Atomic Vendor")
        product = self._product("Flour", unit="kg")
        self._link(supplier, product.id)

        lists_before = self.db.execute(
            select(func.count()).select_from(PurchaseReminderList)
        ).scalar_one()
        items_before = self.db.execute(
            select(func.count()).select_from(PurchaseReminderItem)
        ).scalar_one()

        bad = self.client.post(
            f"/api/v1/suppliers/{supplier}/reminders/quick-save",
            json={
                "title": "Broken",
                "items": [
                    {"product_id": product.id, "quantity": 4},
                    {"product_id": "missing-product", "quantity": 1},
                ],
            },
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(
            self.db.execute(
                select(func.count()).select_from(PurchaseReminderList)
            ).scalar_one(),
            lists_before,
        )
        self.assertEqual(
            self.db.execute(
                select(func.count()).select_from(PurchaseReminderItem)
            ).scalar_one(),
            items_before,
        )

    # -- 5. quantity validation ---------------------------------------------
    def test_quantity_must_be_positive_on_create_update_and_quick_save(self):
        supplier = self._supplier("Qty Vendor")
        product = self._product("Nuts", unit="kg")
        self._link(supplier, product.id)
        reminder_list = self._list(supplier)

        self.assertEqual(
            self._item(reminder_list, product_id=product.id, quantity=0).status_code, 422
        )
        self.assertEqual(
            self._item(reminder_list, product_id=product.id, quantity=-1).status_code, 422
        )
        created = self._item(reminder_list, product_id=product.id, quantity=2)
        self.assertEqual(created.status_code, 201, created.text)
        item_id = created.json()["id"]

        for bad in (0, -2):
            response = self.client.patch(
                f"/api/v1/suppliers/reminders/{reminder_list}/items/{item_id}",
                json={"quantity": bad},
            )
            self.assertEqual(response.status_code, 422, response.text)

        patched = self.client.patch(
            f"/api/v1/suppliers/reminders/{reminder_list}/items/{item_id}",
            json={"quantity": 2.5},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(float(patched.json()["quantity"]), 2.5)

        bad_quick_save = self.client.post(
            f"/api/v1/suppliers/{supplier}/reminders/quick-save",
            json={"title": "Zero", "items": [{"product_id": product.id, "quantity": 0}]},
        )
        self.assertEqual(bad_quick_save.status_code, 422, bad_quick_save.text)

    # -- 6. delete list -----------------------------------------------------
    def test_delete_list_removes_items_without_touching_stock(self):
        supplier = self._supplier("Delete Vendor")
        product = self._product("Tea", unit="box", stock=9)
        self._link(supplier, product.id)
        reminder_list = self._list(supplier)
        saved = self.client.post(
            f"/api/v1/suppliers/{supplier}/reminders/quick-save",
            json={
                "title": "To delete",
                "items": [{"product_id": product.id, "quantity": 3}],
            },
        )
        self.assertEqual(saved.status_code, 201, saved.text)
        extra_list = self._list(supplier, "Keep me")

        deleted = self.client.delete(
            f"/api/v1/suppliers/reminders/{reminder_list}"
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["message"], "Reminder list deleted")

        self.assertIsNone(self.db.get(PurchaseReminderList, reminder_list))
        self.assertEqual(
            self.db.execute(
                select(func.count())
                .select_from(PurchaseReminderItem)
                .where(PurchaseReminderItem.list_id == reminder_list)
            ).scalar_one(),
            0,
        )
        self.assertIsNotNone(self.db.get(PurchaseReminderList, extra_list))
        self.db.refresh(product)
        self.assertEqual(float(product.stock), 9.0)
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(StockMovement)).scalar_one(),
            0,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/suppliers/reminders/{reminder_list}"
            ).status_code,
            404,
        )

    # -- 7. carry-forward ---------------------------------------------------
    def test_carry_forward_copies_only_pending_items(self):
        supplier = self._supplier("Forward Vendor")
        product = self._product("Coffee", unit="kg", stock=4)
        other_product = self._product("Tea leaves", unit="kg")
        self._link(supplier, product.id)
        self._link(supplier, other_product.id)
        reminder_list = self._list(supplier, "Week 1")

        purchased = self._item(
            reminder_list, name="Purchased coffee", product_id=product.id,
            quantity=1, unit="kg",
        ).json()
        pending_a = self._item(
            reminder_list, name="Coffee", product_id=other_product.id,
            quantity=2, unit="250 g",
        ).json()
        pending_b = self._item(
            reminder_list, name="Custom unfinished", quantity=6, unit="pcs"
        ).json()

        patched = self.client.patch(
            f"/api/v1/suppliers/reminders/{reminder_list}/items/{purchased['id']}",
            json={"is_purchased": True},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.client.patch(
            f"/api/v1/suppliers/reminders/{reminder_list}/items/{pending_a['id']}",
            json={"notes": "remember this"},
        )

        response = self.client.post(
            f"/api/v1/suppliers/reminders/{reminder_list}/carry-forward"
        )
        self.assertEqual(response.status_code, 201, response.text)
        new_list = response.json()
        self.assertEqual(new_list["title"], "Week 1 (next visit)")
        self.assertEqual(new_list["status"], "pending")
        self.assertEqual(new_list["supplier_id"], supplier)
        self.assertEqual(len(new_list["items"]), 2)

        copied = {item["name"]: item for item in new_list["items"]}
        self.assertNotIn("Purchased coffee", copied)  # purchased item not copied
        self.assertEqual(float(copied["Coffee"]["quantity"]), 2.0)
        self.assertEqual(copied["Coffee"]["unit"], "250 g")
        self.assertEqual(copied["Coffee"]["notes"], "remember this")
        self.assertEqual(copied["Coffee"]["product_id"], other_product.id)
        self.assertFalse(copied["Coffee"]["is_purchased"])
        self.assertEqual(float(copied["Custom unfinished"]["quantity"]), 6.0)

        # Original is untouched and stock never moved.
        original_items = self.db.execute(
            select(PurchaseReminderItem)
            .where(PurchaseReminderItem.list_id == reminder_list)
            .order_by(PurchaseReminderItem.created_at.asc(), PurchaseReminderItem.id.asc())
        ).scalars().all()
        self.assertEqual(len(original_items), 3)
        self.db.refresh(product)
        self.assertEqual(float(product.stock), 4.0)
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(StockMovement)).scalar_one(),
            0,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/suppliers/reminders/not-a-list/carry-forward"
            ).status_code,
            404,
        )

    # -- 8. convert-to-purchase is the only stock writer --------------------
    def test_saving_and_ticking_never_change_stock(self):
        supplier = self._supplier("Stock Vendor")
        product = self._product("Rice", unit="kg", stock=7)
        self._link(supplier, product.id)

        saved = self.client.post(
            f"/api/v1/suppliers/{supplier}/reminders/quick-save",
            json={
                "title": "Restock",
                "items": [{"product_id": product.id, "quantity": 5}],
            },
        )
        self.assertEqual(saved.status_code, 201, saved.text)
        item_id = saved.json()["items"][0]["id"]
        list_id = saved.json()["id"]

        # tick + edit quantity through the legacy endpoints
        self.assertEqual(
            self.client.patch(
                f"/api/v1/suppliers/reminders/{list_id}/items/{item_id}",
                json={"is_purchased": True, "quantity": 12},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/suppliers/reminders/{list_id}/items",
                json={"name": "Rice", "product_id": product.id, "quantity": 1},
            ).status_code,
            200,
        )

        self.db.refresh(product)
        self.assertEqual(float(product.stock), 7.0)
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(StockMovement)).scalar_one(),
            0,
        )
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(SupplierPurchase)).scalar_one(),
            0,
        )


class SupplierUnitMigrationTests(unittest.TestCase):
    def test_unit_columns_are_added_additively_to_legacy_tables(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE products ("
                    "id VARCHAR(36) PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                    "price NUMERIC(14,2) NOT NULL, created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO products (id, name, price, created_at, updated_at) "
                    "VALUES ('legacy-product', 'Legacy', 10, '2020-01-01', '2020-01-01')"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE supplier_products ("
                    "id VARCHAR(36) PRIMARY KEY, supplier_id VARCHAR(36), "
                    "product_id VARCHAR(36), created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO supplier_products "
                    "(id, supplier_id, product_id, created_at, updated_at) "
                    "VALUES ('legacy-link', 's1', 'legacy-product', "
                    "'2020-01-01', '2020-01-01')"
                )
            )

        run_migrations(engine)
        run_migrations(engine)  # idempotent

        product_columns = {c["name"] for c in inspect(engine).get_columns("products")}
        link_columns = {
            c["name"] for c in inspect(engine).get_columns("supplier_products")
        }
        self.assertIn("unit", product_columns)
        self.assertIn("unit", link_columns)

        with engine.connect() as conn:
            product = conn.execute(
                text("SELECT name, unit FROM products WHERE id = 'legacy-product'")
            ).one()
            self.assertEqual(product[0], "Legacy")
            self.assertEqual(product[1], "pcs")
            link = conn.execute(
                text("SELECT product_id, unit FROM supplier_products WHERE id = 'legacy-link'")
            ).one()
            self.assertEqual(link[0], "legacy-product")
            self.assertIsNone(link[1])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
