from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class PaymentCreate(BaseModel):
    """Staff records an offline/alternate-mode payment (cash, card, UPI with UTR)."""

    invoice_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    method: str = Field(
        default="upi",
        pattern="^(upi|cash|card|bank_transfer|netbanking|other)$",
    )
    reference: str | None = Field(default=None, max_length=100)
    payer_vpa: str | None = Field(default=None, max_length=120)
    payment_date: date | None = None
    notes: str | None = None
    # Staff recording a payment is trusted; it is confirmed immediately.
    confirm: bool = True


class PaymentOut(ORMModel):
    id: str
    business_id: str
    invoice_id: str
    invoice_number: str | None = None
    customer_id: str
    customer_name: str | None = None
    amount: float
    method: str
    status: str
    reference: str | None = None
    payer_vpa: str | None = None
    payment_date: date | None = None
    notes: str | None = None
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    created_at: datetime


class ConfirmPaymentRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    notes: str | None = None


class PublicPaymentSubmit(BaseModel):
    """A customer *declares* a payment through the public invoice link.

    This NEVER confirms the payment — it only creates a `submitted` record that
    a staff member or a verified webhook must subsequently confirm."""

    amount: float = Field(gt=0)
    method: str = Field(
        default="upi",
        pattern="^(upi|cash|card|bank_transfer|netbanking|other)$",
    )
    reference: str = Field(min_length=4, max_length=100)
    payer_vpa: str | None = Field(default=None, max_length=120)
    notes: str | None = None

    @field_validator("reference")
    @classmethod
    def clean_ref(cls, v: str) -> str:
        return v.strip()


class PublicInvoiceOut(ORMModel):
    invoice_number: str
    transaction_ref: str | None = None
    issue_date: date
    due_date: date | None = None
    status: str
    total_amount: float
    paid_amount: float
    balance_amount: float
    customer_name: str | None = None
    business_name: str = ""
    business_upi_id: str | None = None
    business_upi_name: str | None = None
    currency: str = "INR"
    items: list = []
    payments: list = []
