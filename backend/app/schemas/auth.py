from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_in: int
    user: "AuthUser"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    """Creates a new business (tenant) together with its owner user."""

    business_name: str = Field(min_length=2, max_length=200)
    owner_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    upi_id: str | None = Field(default=None, max_length=120)
    gstin: str | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class AuthUser(ORMModel):
    id: str
    business_id: str
    full_name: str
    email: str
    role: str
    business_name: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: str
    business_id: str
    full_name: str
    email: str
    phone: str | None = None
    role: str
    is_active: bool
    created_at: datetime


TokenResponse.model_rebuild()
