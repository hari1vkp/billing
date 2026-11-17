from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_info(request: Request):
    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return ua, ip


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    try:
        return auth_service.register(db, data)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ua, ip = _client_info(request)
    try:
        return auth_service.login(db, data.email, data.password, ua, ip)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    ua, ip = _client_info(request)
    try:
        return auth_service.refresh(db, data.refresh_token, ua, ip)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/logout", response_model=MessageResponse)
def logout(data: RefreshRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, data.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_service.logout_all(db, user.id)
    return MessageResponse(message="All sessions revoked")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        auth_service.change_password(db, user, data.current_password, data.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MessageResponse(message="Password changed. Please sign in again.")
