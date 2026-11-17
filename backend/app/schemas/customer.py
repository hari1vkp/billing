from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = Field(default=None, max_length=20)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class CustomerOut(ORMModel):
    id: str
    business_id: str
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerStats(BaseModel):
    total_purchases: float = 0
    invoice_count: int = 0
    outstanding_balance: float = 0
    total_paid: float = 0
    last_transaction_date: date | None = None
    last_invoice_date: date | None = None


class CustomerDetail(CustomerOut):
    stats: CustomerStats
    interactions: list["InteractionOut"] = []


class InteractionCreate(BaseModel):
    type: str = Field(default="note", pattern="^(note|call|email|meeting|other)$")
    content: str = Field(min_length=1, max_length=5000)


class InteractionOut(ORMModel):
    id: str
    type: str
    content: str
    created_by: str | None = None
    created_at: datetime


CustomerDetail.model_rebuild()
