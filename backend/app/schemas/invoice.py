from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class InvoiceItemCreate(BaseModel):
    product_id: str | None = None
    # POS scanners can send a barcode instead of a product id; the service
    # resolves it within the current business.
    barcode: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=300)
    quantity: float = Field(gt=0)
    unit_price: float | None = Field(default=None, ge=0)
    discount_percent: float = Field(default=0, ge=0, le=100)
    gst_rate: float | None = Field(default=None, ge=0, le=100)


class InvoiceCreate(BaseModel):
    # Optional for fast POS billing; a per-business "Walk-in Customer" is
    # created/reused when omitted.
    customer_id: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    items: list[InvoiceItemCreate] = Field(min_length=1)
    discount_percent: float = Field(default=0, ge=0, le=100)
    invoice_number: str | None = Field(default=None, max_length=50)
    transaction_ref: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    status: str = Field(default="unpaid", pattern="^(draft|unpaid)$")
    pricing_mode: str = Field(default="retail", pattern="^(retail|wholesale)$")

    @field_validator("due_date")
    @classmethod
    def check_dates(cls, v: date | None, info) -> date | None:
        issue = info.data.get("issue_date")
        if v and issue and v < issue:
            raise ValueError("due_date cannot be before issue_date")
        return v


class InvoiceUpdate(BaseModel):
    customer_id: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    items: list[InvoiceItemCreate] | None = Field(default=None, min_length=1)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    pricing_mode: str | None = Field(default=None, pattern="^(retail|wholesale)$")


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|unpaid|cancelled)$")


class InvoiceItemOut(ORMModel):
    id: str
    invoice_id: str
    product_id: str | None = None
    description: str
    quantity: float
    unit_price: float
    discount_percent: float
    discount_amount: float
    wholesale_discount_percent: float = 0
    taxable_amount: float
    gst_rate: float
    tax_amount: float
    line_total: float
    sort_order: int


class InvoiceOut(ORMModel):
    id: str
    business_id: str
    customer_id: str
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    invoice_number: str
    transaction_ref: str | None = None
    issue_date: date
    due_date: date | None = None
    status: str
    pricing_mode: str = "retail"
    subtotal: float
    discount_percent: float = 0
    discount_amount: float
    taxable_amount: float
    tax_amount: float
    total_amount: float
    paid_amount: float
    balance_amount: float
    notes: str | None = None
    public_token: str
    created_at: datetime
    updated_at: datetime
    items: list[InvoiceItemOut] = []


class InvoiceListItem(ORMModel):
    id: str
    invoice_number: str
    transaction_ref: str | None = None
    customer_id: str
    customer_name: str | None = None
    issue_date: date
    due_date: date | None = None
    status: str
    pricing_mode: str = "retail"
    total_amount: float
    paid_amount: float
    balance_amount: float
    created_at: datetime
