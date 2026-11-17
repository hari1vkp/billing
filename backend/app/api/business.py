from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import get_db
from app.core.deps import get_current_user, require_owner
from app.models.business import Business
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.business import (
    BusinessOut,
    BusinessUpdate,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.schemas.common import MessageResponse
from app.services import audit_service

router = APIRouter(prefix="/business", tags=["Business & Settings"])


@router.get("", response_model=BusinessOut)
def get_business(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    business = db.get(Business, user.business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


@router.patch("", response_model=BusinessOut)
def update_business(
    data: BusinessUpdate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    business = db.get(Business, user.business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(business, key, value)
    if data.upi_id and not data.upi_name and not business.upi_name:
        business.upi_name = business.name
    db.flush()
    audit_service.log_activity(
        db,
        business.id,
        user_id=user.id,
        action="business.update",
        category="business",
        reference=business.name,
        entity_type="business",
        entity_id=business.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return business


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    return list(
        db.execute(
            select(User).where(User.business_id == user.business_id).order_by(User.created_at)
        ).scalars().all()
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreateRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    exists = db.execute(select(User).where(User.email == data.email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Email already in use")
    new_user = User(
        business_id=user.business_id,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        hashed_password=security.hash_password(data.password),
        role=data.role,
    )
    db.add(new_user)
    db.flush()
    audit_service.log_activity(
        db,
        user.business_id,
        user_id=user.id,
        action="staff.create",
        category="staff",
        reference=new_user.email,
        entity_type="user",
        entity_id=new_user.id,
        details={"full_name": new_user.full_name, "role": new_user.role},
    )
    return new_user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    data: UserUpdateRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    target = db.execute(
        select(User).where(User.id == user_id, User.business_id == user.business_id)
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(target, key, value)
    db.flush()
    audit_service.log_activity(
        db,
        user.business_id,
        user_id=user.id,
        action="staff.update",
        category="staff",
        reference=target.email,
        entity_type="user",
        entity_id=target.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return target


@router.delete("/users/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    target = db.execute(
        select(User).where(User.id == user_id, User.business_id == user.business_id)
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_active = False
    db.flush()
    audit_service.log_activity(
        db,
        user.business_id,
        user_id=user.id,
        action="staff.deactivate",
        category="staff",
        reference=target.email,
        entity_type="user",
        entity_id=target.id,
        details={"full_name": target.full_name},
    )
    return MessageResponse(message="User deactivated")
