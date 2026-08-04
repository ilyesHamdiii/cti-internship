from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, refresh_user
from app.core.config import get_settings
from app.core.security import create_token, verify_password
from app.db.session import get_db
from app.models.models import User
from app.schemas.api import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    settings = get_settings()
    return TokenResponse(
        access_token=create_token(user.id, user.role.value, settings.access_token_minutes, "access"),
        refresh_token=create_token(user.id, user.role.value, settings.refresh_token_minutes, "refresh"),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(user: User = Depends(refresh_user)) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_token(user.id, user.role.value, settings.access_token_minutes, "access"),
        refresh_token=create_token(user.id, user.role.value, settings.refresh_token_minutes, "refresh"),
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, display_name=user.display_name, role=user.role.value)
