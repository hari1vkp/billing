from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, Field, computed_field, model_validator

from app.schemas.common import ORMModel


def _round_money(value) -> float:
    """Same two-decimal, half-up rounding used by the invoice amount engine."""
    return float(
        Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="pcs", min_length=1, max_length=32)
    sku: str | None = Field(default=None, max_length=50)
    barcode: str | None = Field(default=None, max_length=64)
    description: str | None = None
    hsn_code: str | None = Field(default=None, max_length=20)
    price: float = Field(ge=0)
    gst_rate: float = Field(default=18, ge=0, le=100)
    stock: float = Field(default=0, ge=0)
    track_inventory: bool = True
    is_service: bool = False
    low_stock_threshold: float = Field(default=10, ge=0)
    discount_type: str = Field(default="none", max_length=16)
    discount_value: float = Field(default=0, ge=0)
    wholesale_discount_percent: float = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def services_have_no_inventory(self) -> "ProductBase":
        if self.is_service:
            self.track_inventory = False
            self.stock = 0
        return self


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    sku: str | None = None
    barcode: str | None = Field(default=None, max_length=64)
    description: str | None = None
    hsn_code: str | None = None
    price: float | None = Field(default=None, ge=0)
    gst_rate: float | None = Field(default=None, ge=0, le=100)
    stock: float | None = Field(default=None, ge=0)
    track_inventory: bool | None = None
    is_service: bool | None = None
    low_stock_threshold: float | None = Field(default=None, ge=0)
    discount_type: str | None = Field(default=None, max_length=16)
    discount_value: float | None = Field(default=None, ge=0)
    wholesale_discount_percent: float | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


class ProductOut(ORMModel):
    id: str
    business_id: str
    name: str
    unit: str = "pcs"
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    hsn_code: str | None = None
    price: float
    gst_rate: float
    stock: float
    track_inventory: bool
    is_service: bool
    low_stock_threshold: float
    discount_type: str
    discount_value: float
    wholesale_discount_percent: float = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def wholesale_price(self) -> float:
        """Derived, never stored: retail price less the wholesale discount."""
        factor = Decimal("1") - (
            Decimal(str(self.wholesale_discount_percent or 0)) / Decimal("100")
        )
        return _round_money(Decimal(str(self.price)) * factor)

    @computed_field
    @property
    def is_low_stock(self) -> bool:
        return bool(self.track_inventory and self.stock <= self.low_stock_threshold)
