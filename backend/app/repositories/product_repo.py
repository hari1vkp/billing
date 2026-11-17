from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    model = Product

    def __init__(self, db: Session):
        super().__init__(db)
        self.db = db

    def search(
        self,
        business_id: str,
        query: str | None,
        low_stock_only: bool,
        skip: int,
        limit: int,
    ):
        stmt = select(Product).where(Product.business_id == business_id)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(like),
                    func.coalesce(Product.sku, "").ilike(like),
                    func.coalesce(Product.barcode, "").ilike(like),
                )
            )
        if low_stock_only:
            stmt = stmt.where(
                Product.track_inventory.is_(True),
                Product.stock <= Product.low_stock_threshold,
            )
        total = self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        items = list(
            self.db.execute(
                stmt.order_by(Product.name.asc()).offset(skip).limit(limit)
            ).scalars().all()
        )
        return items, total

    def low_stock_count(self, business_id: str) -> int:
        return int(
            self.db.execute(
                select(func.count()).where(
                    Product.business_id == business_id,
                    Product.track_inventory.is_(True),
                    Product.stock <= Product.low_stock_threshold,
                )
            ).scalar_one()
        )

    def decrement_stocks(self, adjustments: list[tuple[str, float]]) -> None:
        """Adjust stock for a list of (product_id, quantity) tuples."""
        for product_id, qty in adjustments:
            product = self.db.get(Product, product_id)
            if product and product.track_inventory:
                product.stock = float(product.stock) - qty
        self.db.flush()
