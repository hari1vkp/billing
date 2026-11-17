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

    with engine.begin() as conn:
        if "products" in table_names:
            columns = {c["name"] for c in inspector.get_columns("products")}
            if "barcode" not in columns:
                logger.info("Migration: adding products.barcode")
                conn.execute(text("ALTER TABLE products ADD COLUMN barcode VARCHAR(64)"))
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

    logger.info("Additive schema migrations complete")
