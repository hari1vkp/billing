"""Pydantic schemas for the supplier management API."""

import re
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

_PHONE_RE = re.compile(r"^[0-9+\-()\s.]{1,40}$")


def _clean_phone(value: str | None) -> str | None:
    """Loose phone validation: strip, allow common phone punctuation only."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _PHONE_RE.fullmatch(value):
        raise ValueError("Enter a valid phone number")
    return value


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=40)
    whatsapp: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    address: str | None = None
    category: str | None = Field(default=None, max_length=100)
    brands: str | None = None
    notes: str | None = None

    @field_validator("phone", "whatsapp", mode="before")
    @classmethod
    def check_phone(cls, v: str | None) -> str | None:
        return _clean_phone(v)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_person: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    category: str | None = None
    brands: str | None = None
    notes: str | None = None
    is_active: bool | None = None

    @field_validator("phone", "whatsapp", mode="before")
    @classmethod
    def check_phone(cls, v: str | None) -> str | None:
        return _clean_phone(v)


class SupplierOut(ORMModel):
    id: str
    business_id: str
    name: str
    contact_person: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    address: str | None = None
    category: str | None = None
    brands: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierListOut(SupplierOut):
    product_count: int = 0


class SupplierProductBase(BaseModel):
    product_id: str | None = Field(default=None, min_length=1)
    custom_name: str | None = Field(default=None, max_length=200)
    # Per-supplier unit override (VARCHAR(32)); null means "use product unit".
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    supplier_sku: str | None = Field(default=None, max_length=80)
    supplier_price: float | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("custom_name", mode="before")
    @classmethod
    def clean_custom_name(cls, v: str | None) -> str | None:
        return _clean_text(v)

    def model_post_init(self, __context) -> None:
        # Either an existing BillFlow product OR a free-text name is required.
        if not self.product_id and not self.custom_name:
            raise ValueError("product_id or custom_name is required")


class SupplierProductCreate(SupplierProductBase):
    pass


class SupplierProductUpdate(BaseModel):
    product_id: str | None = Field(default=None, min_length=1)
    custom_name: str | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    supplier_sku: str | None = None
    supplier_price: float | None = Field(default=None, ge=0)
    notes: str | None = None


class SupplierProductOut(ORMModel):
    id: str
    business_id: str
    supplier_id: str
    product_id: str | None = None
    custom_name: str | None = None
    unit: str | None = None
    supplier_sku: str | None = None
    supplier_price: float | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierProductCardOut(SupplierProductOut):
    """Enriched supplier-product row for the reminder selection cards.

    Every field is derived from the existing supplier-product link and its
    product. Brand/category/variant/size come only from product description
    metadata that was explicitly stored there; they are never invented.
    """

    product_name: str | None = None
    product_brand: str | None = None
    product_category: str | None = None
    product_variant: str | None = None
    product_size_pack: str | None = None
    product_unit: str | None = None
    unit: str | None = None  # supplier override, else product unit


class ReminderListCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ReminderListUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None
    status: str | None = Field(default=None, pattern="^(pending|converted)$")


class QuickSaveItemIn(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    expected_price: float | None = Field(default=None, ge=0)
    notes: str | None = None


class QuickSaveIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    items: list[QuickSaveItemIn] = []

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ReminderItemCreate(BaseModel):
    product_id: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0)
    unit: str | None = Field(default=None, max_length=50)
    expected_price: float | None = Field(default=None, ge=0)
    notes: str | None = None
    is_purchased: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ReminderItemUpdate(BaseModel):
    product_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    expected_price: float | None = Field(default=None, ge=0)
    notes: str | None = None
    is_purchased: bool | None = None


class ReminderItemOut(ORMModel):
    id: str
    business_id: str
    list_id: str
    product_id: str | None = None
    name: str
    quantity: float
    unit: str | None = None
    expected_price: float | None = None
    notes: str | None = None
    is_purchased: bool
    created_at: datetime
    updated_at: datetime


class ReminderListOut(ORMModel):
    id: str
    business_id: str
    supplier_id: str
    title: str
    status: str
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ReminderItemOut] = []


class VisitCreate(BaseModel):
    visit_date: date | None = None
    discussion_notes: str | None = None
    items_discussed: str | None = None
    items_requested: str | None = None
    follow_up: str | None = None
    next_visit_date: date | None = None
    notes: str | None = None


class VisitUpdate(BaseModel):
    visit_date: date | None = None
    discussion_notes: str | None = None
    items_discussed: str | None = None
    items_requested: str | None = None
    follow_up: str | None = None
    next_visit_date: date | None = None
    notes: str | None = None


class VisitOut(ORMModel):
    id: str
    business_id: str
    supplier_id: str
    visit_date: date
    discussion_notes: str | None = None
    items_discussed: str | None = None
    items_requested: str | None = None
    follow_up: str | None = None
    next_visit_date: date | None = None
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierDetail(SupplierOut):
    products: list[SupplierProductOut] = []
    reminder_lists: list[ReminderListOut] = []
    visits: list[VisitOut] = []


class CategoryDiscovery(BaseModel):
    """Distinct, user-defined values derived from stored supplier rows."""

    categories: list[str] = []
    brands: list[str] = []
    product_types: list[str] = []


class ConvertToPurchaseIn(BaseModel):
    purchase_date: date | None = None
    notes: str | None = None
    only_purchased: bool = True


class SupplierPurchaseItemOut(ORMModel):
    id: str
    business_id: str
    purchase_id: str
    product_id: str | None = None
    quantity: float
    unit_price: float
    line_total: float
    reminder_item_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierPurchaseOut(ORMModel):
    id: str
    business_id: str
    supplier_id: str
    purchase_number: str
    purchase_date: date
    reminder_list_id: str | None = None
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[SupplierPurchaseItemOut] = []
    stock_movements: int = 0


SupplierDetail.model_rebuild()
ReminderListOut.model_rebuild()
SupplierPurchaseOut.model_rebuild()
