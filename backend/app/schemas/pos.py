"""Schemas for the simplified cashier checkout (two tabs, one action)."""

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from app.schemas.invoice import InvoiceItemCreate, InvoiceOut
from app.schemas.payment import PaymentOut


class PosCartItem(InvoiceItemCreate):
    """A cart line — product_id is the normal source for price and GST."""


class PosQuoteRequest(BaseModel):
    customer_id: str | None = None
    items: list[PosCartItem] = Field(min_length=1)
    discount_percent: float = Field(default=0, ge=0, le=100)
    pricing_mode: str = Field(default="retail", pattern="^(retail|wholesale)$")
    transaction_ref: str | None = Field(default=None, max_length=100)


class PosQRResponse(BaseModel):
    qr_data_url: str
    upi_uri: str
    amount: float
    upi_id: str
    upi_name: str
    business_name: str
    transaction_ref: str
    currency: str = "INR"
    quote: dict


class PosCheckoutRequest(PosQuoteRequest):
    method: str = Field(pattern="^(upi|cash)$")
    notes: str | None = None

    @field_validator("method")
    @classmethod
    def lower_method(cls, v: str) -> str:
        return v.strip().lower()


class PosCheckoutResponse(BaseModel):
    invoice: InvoiceOut
    payment: PaymentOut
    receipt: "Receipt"


class Receipt(ORMModel):
    invoice_number: str
    transaction_ref: str | None = None
    business_name: str
    customer_name: str | None = None
    amount: float
    method: str
    reference: str | None = None
    payment_date: date | None = None
    status: str = "paid"
    note: str = "Payment recorded and confirmed manually by the cashier."


PosCheckoutResponse.model_rebuild()
