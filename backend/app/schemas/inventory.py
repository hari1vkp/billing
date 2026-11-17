from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StockAdjustCreate(BaseModel):
    product_id: str = Field(min_length=1)
    quantity_change: float
    reason: str = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=500)


class StockMovementOut(ORMModel):
    id: str
    business_id: str
    product_id: str | None = None
    product_name: str
    sku: str | None = None
    barcode: str | None = None
    quantity_change: float
    quantity_before: float
    quantity_after: float
    reason: str
    reference: str | None = None
    performed_by: str | None = None
    performed_by_name: str
    notes: str | None = None
    created_at: datetime
