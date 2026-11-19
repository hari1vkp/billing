"""Non-destructive, additive startup migrations.

Existing tables and rows are never dropped, recreated or rewritten. This
helper only:

  1. creates tables that do not exist yet (via ``metadata.create_all``),
  2. adds missing columns to *pre-existing* tables with plain ``ALTER TABLE``,
  3. backfills newly added columns from data that already exists,
  4. creates the new indexes with ``CREATE INDEX IF NOT EXISTS``.

It is safe to run on every startup and on an empty database.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.database import Base

logger = logging.getLogger(__name__)


def run_migrations(engine: Engine) -> None:
    """Bring an existing database up to the current schema, additively."""

    # 1. create_all is idempotent and never alters/drops existing tables.
    #    It creates the brand-new stock_movements / activity_logs tables.
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    # Read supplier-table column info BEFORE opening the write transaction:
    # with SQLite in-memory databases the inspector shares the pool connection,
    # and querying it mid-transaction can close that connection underneath us.
    _supplier_table_names = (
        "suppliers",
        "supplier_products",
        "purchase_reminder_lists",
        "purchase_reminder_items",
        "supplier_visits",
        "supplier_purchases",
        "supplier_purchase_items",
    )
    supplier_existing_columns = {
        name: {c["name"] for c in inspector.get_columns(name)}
        for name in _supplier_table_names
        if name in table_names
    }

    with engine.begin() as conn:
        if "products" in table_names:
            columns = {c["name"] for c in inspector.get_columns("products")}
            if "barcode" not in columns:
                logger.info("Migration: adding products.barcode")
                conn.execute(text("ALTER TABLE products ADD COLUMN barcode VARCHAR(64)"))
            if "discount_type" not in columns:
                logger.info("Migration: adding products.discount_type")
                conn.execute(
                    text(
                        "ALTER TABLE products ADD COLUMN discount_type "
                        "VARCHAR(16) DEFAULT 'none'"
                    )
                )
            if "discount_value" not in columns:
                logger.info("Migration: adding products.discount_value")
                conn.execute(
                    text(
                        "ALTER TABLE products ADD COLUMN discount_value "
                        "NUMERIC(14,2) DEFAULT 0"
                    )
                )
            if "wholesale_discount_percent" not in columns:
                logger.info("Migration: adding products.wholesale_discount_percent")
                conn.execute(
                    text(
                        "ALTER TABLE products ADD COLUMN wholesale_discount_percent "
                        "NUMERIC(5,2) NOT NULL DEFAULT 0"
                    )
                )
            if "unit" not in columns:
                logger.info("Migration: adding products.unit")
                conn.execute(
                    text(
                        "ALTER TABLE products ADD COLUMN unit "
                        "VARCHAR(32) NOT NULL DEFAULT 'pcs'"
                    )
                )
            # create_all only creates this index when it creates the table; for
            # a pre-existing products table we create it explicitly here.
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_products_barcode ON products (barcode)")
            )

        if "invoices" in table_names:
            columns = {c["name"] for c in inspector.get_columns("invoices")}
            if "transaction_ref" not in columns:
                logger.info("Migration: adding invoices.transaction_ref and backfilling")
                conn.execute(
                    text("ALTER TABLE invoices ADD COLUMN transaction_ref VARCHAR(100)")
                )
                conn.execute(
                    text(
                        "UPDATE invoices SET transaction_ref = invoice_number "
                        "WHERE transaction_ref IS NULL"
                    )
                )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_invoices_transaction_ref "
                    "ON invoices (transaction_ref)"
                )
            )
            if "pricing_mode" not in columns:
                logger.info("Migration: adding invoices.pricing_mode")
                conn.execute(
                    text(
                        "ALTER TABLE invoices ADD COLUMN pricing_mode "
                        "VARCHAR(16) NOT NULL DEFAULT 'retail'"
                    )
                )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_invoices_pricing_mode "
                    "ON invoices (pricing_mode)"
                )
            )

        if "invoice_items" in table_names:
            columns = {c["name"] for c in inspector.get_columns("invoice_items")}
            if "wholesale_discount_percent" not in columns:
                logger.info("Migration: adding invoice_items.wholesale_discount_percent")
                conn.execute(
                    text(
                        "ALTER TABLE invoice_items ADD COLUMN "
                        "wholesale_discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0"
                    )
                )

    with engine.begin() as conn:
        # Supplier management tables. ``create_all`` above creates them on a fresh
        # database; the block below makes startup idempotent even if a partially
        # built database already contains one of these tables (legacy/partial
        # installs): only missing columns are added, nothing is ever dropped.
        supplier_table_columns = {
            "suppliers": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "name": "VARCHAR(200) NOT NULL DEFAULT ''",
                "contact_person": "VARCHAR(150)",
                "phone": "VARCHAR(40)",
                "whatsapp": "VARCHAR(40)",
                "email": "VARCHAR(255)",
                "address": "TEXT",
                "category": "VARCHAR(100)",
                "brands": "TEXT",
                "notes": "TEXT",
                "is_active": "BOOLEAN NOT NULL DEFAULT 1",
            },
            "supplier_products": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "supplier_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "product_id": "VARCHAR(36)",
                "custom_name": "VARCHAR(200)",
                "unit": "VARCHAR(32)",
                "supplier_sku": "VARCHAR(80)",
                "supplier_price": "NUMERIC(14,2)",
                "notes": "TEXT",
            },
            "purchase_reminder_lists": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "supplier_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "title": "VARCHAR(200) NOT NULL DEFAULT ''",
                "status": "VARCHAR(16) NOT NULL DEFAULT 'pending'",
                "notes": "TEXT",
                "created_by": "VARCHAR(36)",
            },
            "purchase_reminder_items": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "list_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "product_id": "VARCHAR(36)",
                "name": "VARCHAR(200) NOT NULL DEFAULT ''",
                "quantity": "NUMERIC(14,3) NOT NULL DEFAULT 0",
                "unit": "VARCHAR(50)",
                "expected_price": "NUMERIC(14,2)",
                "notes": "TEXT",
                "is_purchased": "BOOLEAN NOT NULL DEFAULT 0",
            },
            "supplier_visits": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "supplier_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "visit_date": "DATE",
                "discussion_notes": "TEXT",
                "items_discussed": "TEXT",
                "items_requested": "TEXT",
                "follow_up": "TEXT",
                "next_visit_date": "DATE",
                "notes": "TEXT",
                "created_by": "VARCHAR(36)",
            },
            "supplier_purchases": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "supplier_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "purchase_number": "VARCHAR(50) NOT NULL DEFAULT ''",
                "purchase_date": "DATE",
                "reminder_list_id": "VARCHAR(36)",
                "notes": "TEXT",
                "created_by": "VARCHAR(36)",
            },
            "supplier_purchase_items": {
                "business_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "purchase_id": "VARCHAR(36) NOT NULL DEFAULT ''",
                "product_id": "VARCHAR(36)",
                "quantity": "NUMERIC(14,3) NOT NULL DEFAULT 0",
                "unit_price": "NUMERIC(14,2) NOT NULL DEFAULT 0",
                "line_total": "NUMERIC(14,2) NOT NULL DEFAULT 0",
                "reminder_item_id": "VARCHAR(36)",
            },
        }
        for table_name, columns in supplier_table_columns.items():
            if table_name not in table_names:
                continue
            existing_columns = supplier_existing_columns.get(table_name, set())
            for column_name, definition in columns.items():
                if column_name not in existing_columns:
                    logger.info("Migration: adding %s.%s", table_name, column_name)
                    conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
                    )

        supplier_indexes = (
            "CREATE INDEX IF NOT EXISTS ix_suppliers_business_id ON suppliers (business_id)",
            "CREATE INDEX IF NOT EXISTS ix_suppliers_category ON suppliers (category)",
            "CREATE INDEX IF NOT EXISTS ix_supplier_products_supplier_id "
            "ON supplier_products (supplier_id)",
            "CREATE INDEX IF NOT EXISTS ix_supplier_products_product_id "
            "ON supplier_products (product_id)",
            "CREATE INDEX IF NOT EXISTS ix_purchase_reminder_lists_supplier_id "
            "ON purchase_reminder_lists (supplier_id)",
            "CREATE INDEX IF NOT EXISTS ix_purchase_reminder_items_list_id "
            "ON purchase_reminder_items (list_id)",
            "CREATE INDEX IF NOT EXISTS ix_purchase_reminder_items_product_id "
            "ON purchase_reminder_items (product_id)",
            "CREATE INDEX IF NOT EXISTS ix_supplier_visits_supplier_id "
            "ON supplier_visits (supplier_id)",
            "CREATE INDEX IF NOT EXISTS ix_supplier_purchases_business_id "
            "ON supplier_purchases (business_id)",
            "CREATE INDEX IF NOT EXISTS ix_supplier_purchase_items_purchase_id "
            "ON supplier_purchase_items (purchase_id)",
        )
        for statement in supplier_indexes:
            table = statement.split(" ON ", 1)[-1].split(" ", 1)[0]
            if table in table_names:
                conn.execute(text(statement))

        # One-time data backfill: older links were created with only a
        # product_id, so the supplier SKU column was empty. Fill it from the
        # linked product's SKU (or barcode) WITHOUT overwriting entered values
        # and WITHOUT touching supplier price (the owner sets that per supplier).
        product_columns = {
            column["name"] for column in inspector.get_columns("products")
        } if "products" in table_names else set()
        if (
            {"supplier_products", "products"}.issubset(table_names)
            and {"sku", "barcode"}.issubset(product_columns)
        ):
            conn.execute(
                text(
                    "UPDATE supplier_products SET supplier_sku = COALESCE("
                    "(SELECT NULLIF(sku, '') FROM products "
                    " WHERE products.id = supplier_products.product_id), "
                    "(SELECT NULLIF(barcode, '') FROM products "
                    " WHERE products.id = supplier_products.product_id)) "
                    "WHERE (supplier_sku IS NULL OR supplier_sku = '') "
                    "AND product_id IS NOT NULL"
                )
            )

        # One supplier cannot link the same real product twice. Custom-name
        # items (product_id IS NULL) are intentionally exempt. Remove any
        # historical duplicates (keeping the oldest link) before adding the
        # partial unique index; reminders store their own product snapshots so
        # dropping a duplicate link cannot damage historical records.
        if "supplier_products" in table_names:
            conn.execute(
                text(
                    "DELETE FROM supplier_products WHERE id IN ("
                    "SELECT id FROM ("
                    "SELECT id, ROW_NUMBER() OVER ("
                    "PARTITION BY business_id, supplier_id, product_id "
                    "ORDER BY id) AS rn "
                    "FROM supplier_products WHERE product_id IS NOT NULL"
                    ") WHERE rn > 1)"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_supplier_product_link ON supplier_products "
                    "(business_id, supplier_id, product_id) "
                    "WHERE product_id IS NOT NULL"
                )
            )

        # StockMovement.reason is a plain VARCHAR(50); no schema change is needed
        # for the new "purchase" reason. Conversion uses the existing receiving
        # path (inventory_service.record_movement), which accepts any reason.

    logger.info("Additive schema migrations complete")
