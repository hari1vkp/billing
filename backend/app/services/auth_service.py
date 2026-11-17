"""Authentication and session/token management."""

from datetime import datetime, timezone
from typing import Optional

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.models.business import Business
from app.models.user import RefreshToken, User
from app.schemas.auth import RegisterRequest, TokenResponse
from app.services import audit_service


class AuthError(Exception):
    pass


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not security.verify_password(password, user.hashed_password):
        return None
    return user


def _issue_tokens(
    db: Session,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    access = security.create_access_token(
        user.id, extra_claims={"bid": user.business_id, "role": user.role}
    )
    refresh_raw, expires_at = security.create_refresh_token(user.id)
    token_hash = security.hash_token(refresh_raw)
    rt = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(rt)
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh_raw,
        access_token_expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "business_id": user.business_id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "business_name": db.get(Business, user.business_id).name,
        },
    )


def login(
    db: Session,
    email: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    user = authenticate(db, email, password)
    if not user:
        raise AuthError("Invalid email or password")
    tokens = _issue_tokens(db, user, user_agent, ip_address)
    audit_service.log_activity(
        db,
        user.business_id,
        user_id=user.id,
        action="auth.login",
        category="auth",
        reference=user.email,
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role},
    )
    return tokens


def register(db: Session, data: RegisterRequest) -> TokenResponse:
    if get_user_by_email(db, data.email):
        raise AuthError("An account with this email already exists")

    business = Business(
        name=data.business_name.strip(),
        legal_name=data.business_name.strip(),
        email=data.email,
        phone=data.phone,
        gstin=data.gstin,
        upi_id=data.upi_id,
        upi_name=data.business_name.strip() if data.upi_id else None,
    )
    db.add(business)
    db.flush()

    owner = User(
        business_id=business.id,
        full_name=data.owner_name.strip(),
        email=data.email,
        phone=data.phone,
        hashed_password=security.hash_password(data.password),
        role="owner",
    )
    db.add(owner)
    db.flush()
    return _issue_tokens(db, owner)


def refresh(
    db: Session,
    raw_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    try:
        payload = security.decode_token(raw_token, expected_type="refresh")
    except jwt.PyJWTError:
        raise AuthError("Invalid or expired refresh token")

    token_hash = security.hash_token(raw_token)
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if record is None:
        raise AuthError("Refresh token is not recognised")
    if record.revoked:
        # Reuse detection: a revoked token being replayed means it may have been
        # stolen. Revoke every session for that user.
        for t in db.execute(
            select(RefreshToken).where(RefreshToken.user_id == record.user_id)
        ).scalars().all():
            t.revoked = True
        db.flush()
        raise AuthError("Refresh token reuse detected; all sessions revoked")
    if record.expires_at < datetime.now(timezone.utc):
        raise AuthError("Refresh token has expired")

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise AuthError("User not found or inactive")

    # Rotate: invalidate the presented token, then issue a fresh pair.
    new_tokens = _issue_tokens(db, user, user_agent, ip_address)
    new_hash = security.hash_token(new_tokens.refresh_token)
    record.revoked = True
    record.replaced_by = new_hash
    db.flush()
    return new_tokens


def logout(db: Session, raw_token: str) -> None:
    token_hash = security.hash_token(raw_token)
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if record:
        record.revoked = True
        db.flush()


def logout_all(db: Session, user_id: str) -> None:
    for record in db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
    ).scalars().all():
        record.revoked = True
    db.flush()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not security.verify_password(current, user.hashed_password):
        raise AuthError("Current password is incorrect")
    user.hashed_password = security.hash_password(new)
    db.flush()
    logout_all(db, user.id)
