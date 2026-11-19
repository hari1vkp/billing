"""General-purpose supplier management: links, reminders and conversion."""

import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all models on the metadata
from app.api import suppliers as suppliers_api
from app.core.database import Base, get_db
from app.core.migration import run_migrations
from app.core.deps import get_current_user, require_owner
from app.models.activity_log import ActivityLog
from app.models.business import Business
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.supplier import (
    PurchaseReminderItem,
    PurchaseReminderList,
    Supplier,
    SupplierProduct,
    SupplierPurchase,
    SupplierPurchaseItem,
    SupplierVisit,
)
from app.models.user import User
from app.schemas.supplier import (
    ConvertToPurchaseIn,
    ReminderItemCreate,
    ReminderItemUpdate,
    ReminderListCreate,
    ReminderListUpdate,
    SupplierCreate,
    SupplierProductCreate,
    SupplierUpdate,
    VisitCreate,
)
from app.services import supplier_service


class SupplierTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        business = Business(name="Test business", default_gst_rate=0.0)
        self.db.add(business)
        self.db.flush()
        self.business_id = business.id

        other = Business(name="Other tenant", default_gst_rate=0.0)
        self.db.add(other)
        self.db.flush()
        self.other_business_id = other.id

        self.user = User(
            business_id=business.id,
            full_name="Shop Owner",
            email="owner@test.local",
            hashed_password="hashed",
            role="owner",
        )
        self.db.add(self.user)
        self.db.flush()
        self.user_id = self.user.id
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -- helpers -----------------------------------------------------------
    def _supplier(self, name="Supplier", **kwargs):
        return supplier_service.create_supplier(
            self.db, self.business_id, SupplierCreate(name=name, **kwargs), self.user_id
        )

    def _product(self, name="Widget", price=100, stock=0):
        product = Product(
            business_id=self.business_id,
            name=name,
            price=price,
            stock=stock,
            gst_rate=0,
        )
        self.db.add(product)
        self.db.flush()
        return product

    def _link(self, supplier, **kwargs):
        return supplier_service.add_supplier_product(
            self.db,
            self.business_id,
            supplier.id,
            SupplierProductCreate(**kwargs),
            self.user_id,
        )

    def _list(self, supplier, title="Visit list"):
        return supplier_service.create_reminder_list(
            self.db,
            self.business_id,
            supplier.id,
            ReminderListCreate(title=title),
            self.user_id,
        )

    def _item(self, reminder_list, name, **kwargs):
        return supplier_service.add_reminder_item(
            self.db,
            self.business_id,
            reminder_list.id,
            ReminderItemCreate(name=name, **kwargs),
            self.user_id,
        )

    def _mark(self, item, purchased=True):
        return supplier_service.update_reminder_item(
            self.db,
            self.business_id,
            item.list_id,
            item.id,
            ReminderItemUpdate(is_purchased=purchased),
            self.user_id,
        )

    # -- categories / discovery --------------------------------------------
    def test_general_business_categories_and_user_defined_discovery(self):
        for name, category in [
            ("Fresh Mart", "grocery"),
            ("Trend Store", "clothing"),
            ("Electro Hub", "electronics"),
            ("Tools Depot", "hardware"),
            ("Paws & Co", "Pet Supplies"),  # entirely user-defined
        ]:
            self._supplier(name, category=category, brands="Acme, Globex" if category == "grocery" else None)
        self.db.commit()

        discovered = supplier_service.discover_categories(self.db, self.business_id)
        self.assertEqual(
            discovered["categories"],
            ["Pet Supplies", "clothing", "electronics", "grocery", "hardware"],
        )
        self.assertEqual(discovered["brands"], ["Acme", "Globex"])
        # No seeded industry list: only values actually stored are returned.
        self.assertNotIn("pharmacy", discovered["categories"])

        grocery, total = supplier_service.list_suppliers(
            self.db, self.business_id, category="grocery"
        )
        self.assertEqual(total, 1)
        self.assertEqual(grocery[0].name, "Fresh Mart")

        found, total = supplier_service.list_suppliers(
            self.db, self.business_id, q="Paws"
        )
        self.assertEqual(total, 1)
        self.assertEqual(found[0].name, "Paws & Co")

        sorted_items, _ = supplier_service.list_suppliers(
            self.db, self.business_id, sort="name", order="desc"
        )
        self.assertEqual(sorted_items[0].name, "Trend Store")

    # -- supplier-product links --------------------------------------------
    def test_multiple_products_and_brands_per_supplier_and_shared_product(self):
        shared = self._product("Rice 1kg", price=60)
        dal = self._product("Dal 1kg", price=120)
        shirt = self._product("Cotton Shirt", price=500)

        s1 = self._supplier("Wholesale Co", brands="BrandA, BrandB")
        s2 = self._supplier("Retail Co", brands="BrandC")
        self._link(s1, product_id=shared.id, supplier_sku="RICE-1", supplier_price=55)
        self._link(s1, product_id=dal.id, supplier_price=110)
        self._link(s1, custom_name="Imported Rice (unlisted)")
        self._link(s2, product_id=shared.id, supplier_price=58)
        self._link(s2, product_id=shirt.id, supplier_price=450)
        self.db.commit()

        links1 = supplier_service.list_supplier_products(self.db, self.business_id, s1.id)
        links2 = supplier_service.list_supplier_products(self.db, self.business_id, s2.id)
        self.assertEqual(len(links1), 3)
        self.assertEqual(len(links2), 2)
        self.assertIn(shared.id, {l.product_id for l in links1})
        self.assertIn(shared.id, {l.product_id for l in links2})

        _, total = supplier_service.list_suppliers(self.db, self.business_id)
        self.assertEqual(total, 2)
        listed = {s.name: s.product_count for s in supplier_service.list_suppliers(
            self.db, self.business_id
        )[0]}
        self.assertEqual(listed, {"Wholesale Co": 3, "Retail Co": 2})

        # Links never create inventory products.
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(Product)).scalar_one(), 3
        )

        with self.assertRaises(supplier_service.ValidationError):
            self._link(s1, product_id="does-not-exist")

    def test_product_type_filter_uses_stored_links(self):
        product = self._product("Bluetooth Speaker")
        supplier = self._supplier("Gadget Supplier")
        self._link(supplier, product_id=product.id)
        self.db.commit()

        matched, total = supplier_service.list_suppliers(
            self.db, self.business_id, product_type="speaker"
        )
        self.assertEqual(total, 1)
        self.assertEqual(matched[0].id, supplier.id)

    # -- reminder carry-forward / purchased flag ---------------------------
    def test_reminder_lists_carry_pending_items_forward(self):
        supplier = self._supplier("Vendor")
        first = self._list(supplier, "Week 1")
        second = self._list(supplier, "Week 2")
        p1 = self._product("Atta", stock=2)
        self._link(supplier, product_id=p1.id)
        item1 = self._item(first, "Atta", product_id=p1.id, quantity=2, unit="bags")
        self._item(first, "Sugar", quantity=1, unit="kg")
        item3 = self._item(second, "Tea", quantity=3, unit="boxes")
        self._mark(item1, True)
        self.db.commit()

        # The unpurchased item and the whole second list stay pending.
        remaining = supplier_service.list_reminder_items(
            self.db, self.business_id, first.id
        )
        self.assertEqual(
            {i.name: i.is_purchased for i in remaining},
            {"Atta": True, "Sugar": False},
        )
        self.assertEqual(
            [i.name for i in supplier_service.list_reminder_items(
                self.db, self.business_id, second.id
            )],
            ["Tea"],
        )

        supplier_service.convert_to_purchase(
            self.db,
            self.business_id,
            self.user,
            first.id,
            ConvertToPurchaseIn(),
        )
        self.db.commit()
        statuses = {
            lst.id: lst.status
            for lst in supplier_service.list_reminder_lists(
                self.db, self.business_id, supplier.id
            )
        }
        self.assertEqual(statuses[first.id], "converted")
        self.assertEqual(statuses[second.id], "pending")
        self.assertEqual(
            [i.name for i in supplier_service.list_reminder_items(
                self.db, self.business_id, second.id
            )],
            ["Tea"],
        )

    def test_marking_purchased_does_not_change_stock_or_create_movement(self):
        product = self._product("Biscuits", stock=5)
        supplier = self._supplier("Snacks Vendor")
        self._link(supplier, product_id=product.id)
        reminder_list = self._list(supplier)
        item = self._item(
            reminder_list,
            "Biscuits",
            product_id=product.id,
            quantity=3,
            unit="packs",
            expected_price=20,
        )
        self.db.commit()

        self._mark(item, True)
        self.db.commit()

        self.db.refresh(product)
        self.assertEqual(float(product.stock), 5.0)
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(StockMovement)).scalar_one(),
            0,
        )
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(SupplierPurchase)).scalar_one(),
            0,
        )

    # -- conversion --------------------------------------------------------
    def test_conversion_creates_real_stock_movements_and_converts_list(self):
        product = self._product("Milk", price=40, stock=5)
        supplier = self._supplier("Dairy Vendor")
        self._link(supplier, product_id=product.id)
        reminder_list = self._list(supplier, "Restock")
        first = self._item(
            reminder_list, "Milk 1L", product_id=product.id, quantity=2,
            unit="pcs", expected_price=45,
        )
        second = self._item(
            reminder_list, "Milk 500ml", product_id=product.id, quantity=3,
            unit="pcs", expected_price=25,
        )
        custom = self._item(
            reminder_list, "Farm eggs (unlisted)", quantity=10, unit="pcs",
            expected_price=5,
        )
        self._mark(first, True)
        self._mark(second, True)
        self._mark(custom, True)
        self.db.commit()

        purchase = supplier_service.convert_to_purchase(
            self.db,
            self.business_id,
            self.user,
            reminder_list.id,
            ConvertToPurchaseIn(notes="Weekly restock"),
        )
        self.db.commit()

        self.assertTrue(purchase.purchase_number.startswith("PUR-"))
        self.assertEqual(purchase.supplier_id, supplier.id)
        self.assertEqual(purchase.reminder_list_id, reminder_list.id)
        self.assertEqual(purchase.purchase_date, date.today())
        self.assertEqual(len(purchase.items), 2)
        self.assertEqual(purchase.stock_movements, 2)
        self.assertIn("Farm eggs (unlisted)", purchase.notes)
        self.assertIn("Weekly restock", purchase.notes)

        self.db.refresh(product)
        self.assertEqual(float(product.stock), 10.0)

        movements = self.db.execute(
            select(StockMovement).order_by(StockMovement.quantity_change)
        ).scalars().all()
        self.assertEqual(len(movements), 2)
        self.assertEqual({m.reason for m in movements}, {"purchase"})
        self.assertEqual({m.reference for m in movements}, {purchase.purchase_number})
        self.assertEqual(
            [(float(m.quantity_before), float(m.quantity_after)) for m in movements],
            [(5.0, 7.0), (7.0, 10.0)],
        )
        self.assertEqual(
            {m.performed_by_name for m in movements}, {"Shop Owner"}
        )

        purchase_items = self.db.execute(select(SupplierPurchaseItem)).scalars().all()
        self.assertEqual(len(purchase_items), 2)
        self.assertEqual(
            sorted(float(i.line_total) for i in purchase_items), [75.0, 90.0]
        )

        self.db.refresh(reminder_list)
        self.assertEqual(reminder_list.status, "converted")
        actions = {row[0] for row in self.db.execute(select(ActivityLog.action))}
        self.assertIn("supplier.purchase.convert", actions)
        self.assertIn("supplier.reminder.convert", actions)

        # Re-converting is rejected and cannot double-receive stock.
        with self.assertRaises(supplier_service.ConflictError):
            supplier_service.convert_to_purchase(
                self.db, self.business_id, self.user, reminder_list.id,
                ConvertToPurchaseIn(),
            )
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(StockMovement)).scalar_one(),
            2,
        )

    def test_conversion_all_when_only_purchased_false(self):
        product = self._product("Nuts", price=100, stock=0)
        supplier = self._supplier("Nuts Vendor")
        self._link(supplier, product_id=product.id)
        reminder_list = self._list(supplier)
        purchased = self._item(
            reminder_list, "Almonds", product_id=product.id, quantity=1
        )
        self._item(reminder_list, "Cashews", product_id=product.id, quantity=2)
        self._mark(purchased, True)
        self.db.commit()

        purchase = supplier_service.convert_to_purchase(
            self.db,
            self.business_id,
            self.user,
            reminder_list.id,
            ConvertToPurchaseIn(only_purchased=False),
        )
        self.db.commit()
        self.assertEqual(purchase.stock_movements, 2)
        self.db.refresh(product)
        self.assertEqual(float(product.stock), 3.0)

    def test_custom_only_reminder_never_creates_inventory_product(self):
        supplier = self._supplier("Artisan Vendor")
        reminder_list = self._list(supplier)
        self._item(reminder_list, "Handmade basket", quantity=2, unit="pcs")
        self._item(reminder_list, "Special sauce", quantity=5, unit="bottles")
        self.db.commit()
        before_products = self.db.execute(
            select(func.count()).select_from(Product)
        ).scalar_one()

        purchase = supplier_service.convert_to_purchase(
            self.db,
            self.business_id,
            self.user,
            reminder_list.id,
            ConvertToPurchaseIn(only_purchased=False),
        )
        self.db.commit()

        self.assertEqual(purchase.items, [])
        self.assertEqual(purchase.stock_movements, 0)
        self.assertIn("Handmade basket", purchase.notes)
        self.assertIn("Special sauce", purchase.notes)
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(Product)).scalar_one(),
            before_products,
        )
        self.assertEqual(
            self.db.execute(select(func.count()).select_from(StockMovement)).scalar_one(),
            0,
        )

    # -- deactivation / tenant scoping -------------------------------------
    def test_deactivation_and_reactivation(self):
        supplier = self._supplier("Old Vendor")
        self.assertTrue(supplier.is_active)
        supplier_service.deactivate_supplier(
            self.db, self.business_id, supplier.id, self.user_id
        )
        self.db.commit()
        self.assertFalse(supplier.is_active)
        self.assertEqual(
            supplier_service.get_supplier(
                self.db, self.business_id, supplier.id
            ).is_active,
            False,
        )

        supplier_service.update_supplier(
            self.db, self.business_id, supplier.id,
            SupplierUpdate(is_active=True), self.user_id,
        )
        self.db.commit()
        self.assertTrue(supplier.is_active)

    def test_other_tenant_cannot_see_supplier(self):
        supplier = self._supplier("Private Vendor")
        self.db.commit()
        with self.assertRaises(supplier_service.NotFoundError):
            supplier_service.get_supplier(
                self.db, self.other_business_id, supplier.id
            )
        with self.assertRaises(supplier_service.NotFoundError):
            supplier_service.list_supplier_products(
                self.db, self.other_business_id, supplier.id
            )

    # -- schema validation -------------------------------------------------
    def test_schema_validation(self):
        with self.assertRaises(PydanticValidationError):
            SupplierCreate(name="Bad", phone="call me maybe")
        with self.assertRaises(PydanticValidationError):
            SupplierProductCreate(custom_name="Thing", supplier_price=-1)
        with self.assertRaises(PydanticValidationError):
            SupplierProductCreate()  # needs a product or custom name
        with self.assertRaises(PydanticValidationError):
            ReminderItemCreate(name="Thing", quantity=-1)
        with self.assertRaises(PydanticValidationError):
            ReminderItemCreate(name="Thing", expected_price=-5)
        with self.assertRaises(PydanticValidationError):
            ReminderListUpdate(status="archived")
        self.assertEqual(
            SupplierCreate(name=" OK ", phone="+91 98765-43210").name, "OK"
        )


    # -- safety improvements ------------------------------------------------
    def test_active_filter_and_reactivation(self):
        active = self._supplier("Active Vendor")
        inactive = self._supplier("Inactive Vendor")
        supplier_service.deactivate_supplier(
            self.db, self.business_id, inactive.id, self.user_id
        )
        self.db.commit()

        active_rows, active_total = supplier_service.list_suppliers(
            self.db, self.business_id, is_active=True
        )
        inactive_rows, inactive_total = supplier_service.list_suppliers(
            self.db, self.business_id, is_active=False
        )
        self.assertEqual(active_total, 1)
        self.assertEqual([s.id for s in active_rows], [active.id])
        self.assertEqual(inactive_total, 1)
        self.assertEqual([s.id for s in inactive_rows], [inactive.id])

        supplier_service.update_supplier(
            self.db,
            self.business_id,
            inactive.id,
            SupplierUpdate(is_active=True),
            self.user_id,
        )
        self.db.commit()
        reactivated, total = supplier_service.list_suppliers(
            self.db, self.business_id, is_active=True
        )
        self.assertEqual(total, 2)
        self.assertIn(inactive.id, [s.id for s in reactivated])

    def test_duplicate_supplier_product_is_rejected(self):
        product = self._product("Soap")
        supplier = self._supplier("Vendor")
        self._link(supplier, product_id=product.id)
        with self.assertRaises(supplier_service.ValidationError):
            self._link(supplier, product_id=product.id)
        # Custom-name items remain allowed and are not considered duplicates.
        self._link(supplier, custom_name="Local handmade item")

    def test_historical_reminder_item_stays_editable_after_unlink(self):
        product = self._product("Atta")
        supplier = self._supplier("Vendor")
        link = self._link(supplier, product_id=product.id)
        reminder_list = self._list(supplier)
        item = self._item(
            reminder_list, "Atta", product_id=product.id, quantity=2, unit="bags"
        )
        self.db.flush()
        self.db.delete(link)
        self.db.commit()

        updated = supplier_service.update_reminder_item(
            self.db,
            self.business_id,
            reminder_list.id,
            item.id,
            ReminderItemUpdate(quantity=5, notes="still needed"),
            self.user_id,
        )
        self.db.commit()
        self.assertEqual(float(updated.quantity), 5.0)
        self.assertEqual(updated.product_id, product.id)

        with self.assertRaises(supplier_service.RelationshipError):
            self._item(
                reminder_list, "Atta again", product_id=product.id, quantity=1
            )

    def test_deactivation_preserves_all_history(self):
        product = self._product("Rice")
        supplier = self._supplier("Vendor")
        self._link(supplier, product_id=product.id)
        reminder_list = self._list(supplier)
        self._item(reminder_list, "Rice", product_id=product.id, quantity=2)
        supplier_service.create_visit(
            self.db,
            self.business_id,
            supplier.id,
            VisitCreate(visit_date=date(2026, 11, 20), discussion_notes="Rates"),
            self.user_id,
        )
        self.db.commit()
        supplier_service.deactivate_supplier(
            self.db, self.business_id, supplier.id, self.user_id
        )
        self.db.commit()

        detail = supplier_service.get_supplier_detail(
            self.db, self.business_id, supplier.id
        )
        self.assertFalse(detail.is_active)
        self.assertEqual(len(detail.products), 1)
        self.assertEqual(len(detail.reminder_lists), 1)
        self.assertEqual(len(detail.visits), 1)



class SupplierApiTests(unittest.TestCase):
    """Smoke-test the router wiring and owner-only dependency."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        business = Business(name="API business", default_gst_rate=0.0)
        self.db.add(business)
        self.db.flush()
        self.business_id = business.id
        self.owner = User(
            business_id=business.id, full_name="Owner", email="owner@api.local",
            hashed_password="x", role="owner",
        )
        self.staff = User(
            business_id=business.id, full_name="Staff", email="staff@api.local",
            hashed_password="x", role="staff",
        )
        self.db.add_all([self.owner, self.staff])
        self.db.commit()

        self.app = FastAPI()
        self.app.include_router(suppliers_api.router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[require_owner] = lambda: self.owner
        self.client = TestClient(self.app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_full_api_flow_and_owner_only(self):
        created = self.client.post(
            "/api/v1/suppliers",
            json={"name": "API Vendor", "category": "grocery", "phone": "555-1000"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        supplier_id = created.json()["id"]

        categories = self.client.get("/api/v1/suppliers/categories")
        self.assertEqual(categories.status_code, 200)
        self.assertIn("grocery", categories.json()["categories"])

        listing = self.client.get("/api/v1/suppliers", params={"q": "Vendor"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)

        reminder = self.client.post(
            f"/api/v1/suppliers/{supplier_id}/reminders", json={"title": "Monday"}
        )
        self.assertEqual(reminder.status_code, 201, reminder.text)
        list_id = reminder.json()["id"]

        item = self.client.post(
            f"/api/v1/suppliers/reminders/{list_id}/items",
            json={"name": "Custom item", "quantity": 2, "unit": "boxes"},
        )
        self.assertEqual(item.status_code, 201, item.text)
        item_id = item.json()["id"]

        ticked = self.client.patch(
            f"/api/v1/suppliers/reminders/{list_id}/items/{item_id}",
            json={"is_purchased": True},
        )
        self.assertEqual(ticked.status_code, 200)
        self.assertTrue(ticked.json()["is_purchased"])

        converted = self.client.post(
            f"/api/v1/suppliers/reminders/{list_id}/convert-to-purchase",
            json={"notes": "API purchase"},
        )
        self.assertEqual(converted.status_code, 200, converted.text)
        self.assertEqual(converted.json()["reminder_list_id"], list_id)

        detail = self.client.get(f"/api/v1/suppliers/{supplier_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["products"], [])
        self.assertEqual(body["reminder_lists"][0]["status"], "converted")
        self.assertEqual(body["visits"], [])

        visit = self.client.post(
            f"/api/v1/suppliers/{supplier_id}/visits",
            json={"discussion_notes": "Discussed prices"},
        )
        self.assertEqual(visit.status_code, 201, visit.text)

        deleted = self.client.delete(f"/api/v1/suppliers/{supplier_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(self.client.get(
            f"/api/v1/suppliers/{supplier_id}"
        ).json()["is_active"])

    def test_staff_is_forbidden(self):
        app = FastAPI()
        app.include_router(suppliers_api.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.staff
        client = TestClient(app)
        response = client.get("/api/v1/suppliers")
        self.assertEqual(response.status_code, 403)


class SupplierMigrationTests(unittest.TestCase):
    def test_supplier_tables_are_added_idempotently_without_data_loss(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE suppliers ("
                    "id VARCHAR(36) PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO suppliers (id, name, created_at, updated_at) "
                    "VALUES ('legacy-1', 'Legacy Vendor', '2020-01-01', '2020-01-01')"
                )
            )

        run_migrations(engine)
        run_migrations(engine)  # must be safe to run repeatedly

        tables = set(inspect(engine).get_table_names())
        for table in (
            "suppliers",
            "supplier_products",
            "purchase_reminder_lists",
            "purchase_reminder_items",
            "supplier_visits",
            "supplier_purchases",
            "supplier_purchase_items",
        ):
            self.assertIn(table, tables)

        columns = {c["name"] for c in inspect(engine).get_columns("suppliers")}
        for column in (
            "business_id", "name", "contact_person", "phone", "whatsapp", "email",
            "address", "category", "brands", "notes", "is_active",
        ):
            self.assertIn(column, columns)

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, is_active FROM suppliers WHERE id = 'legacy-1'")
            ).one()
            self.assertEqual(row[0], "Legacy Vendor")
            self.assertEqual(row[1], 1)
        engine.dispose()

if __name__ == "__main__":
    unittest.main()
