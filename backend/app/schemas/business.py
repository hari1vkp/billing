from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class BusinessOut(ORMModel):
    id: str
    name: str
    legal_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    logo_url: str | None = None
    upi_id: str | None = None
    upi_name: str | None = None
    currency: str
    invoice_prefix: str
    invoice_footer: str | None = None
    default_gst_rate: float
    low_stock_threshold: int
    created_at: datetime


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    legal_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    upi_id: str | None = None
    upi_name: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    invoice_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    invoice_footer: str | None = None
    default_gst_rate: float | None = Field(default=None, ge=0, le=100)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class UserCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str | None = None
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="staff", pattern="^(owner|staff)$")

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(owner|staff)$")
