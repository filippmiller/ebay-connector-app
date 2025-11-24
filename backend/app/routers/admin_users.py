from __future__ import annotations

from typing import List, Optional
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import User as UserDB, UserRole as UserRoleEnum
from app.models.user import UserResponse
from app.services.auth import get_password_hash
from app.services.auth import admin_required
from app.utils.logger import logger

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


class AdminUserCreatePayload:
    email: str
    username: str
    role: str  # 'admin' | 'user' | other roles if needed
    temporary_password: Optional[str] = None


@router.get("/", response_model=List[UserResponse])
async def list_users(_: UserResponse = Depends(admin_required), db: Session = Depends(get_db)):
    users = db.query(UserDB).order_by(UserDB.created_at.asc()).all()
    results: List[UserResponse] = []
    for u in users:
        results.append(
            UserResponse(
                id=u.id,
                email=u.email,
                username=u.username,
                role=u.role,
                is_active=getattr(u, "is_active", True),
                must_change_password=getattr(u, "must_change_password", False),
                created_at=u.created_at,
                ebay_connected=u.ebay_connected,
            )
        )
    return results


@router.post("/create")
async def create_user_admin(payload: dict, _: UserResponse = Depends(admin_required), db: Session = Depends(get_db)):
    """Create a new user with a temporary password set by admin.

    Returns the generated temporary password once so the admin can pass
    it to the user out-of-band.
    """
    email = (payload.get("email") or "").strip().lower()
    username = (payload.get("username") or "").strip()
    role_raw = (payload.get("role") or "user").strip().lower()
    temp_password = payload.get("temporary_password") or None

    if not email or not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email and username are required")

    existing = db.query(UserDB).filter(UserDB.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email already exists")

    # Map role string to enum/value
    try:
        if hasattr(UserRoleEnum, role_raw):
            role_value = getattr(UserRoleEnum, role_raw)
        else:
            role_value = UserRoleEnum.user
    except Exception:
        role_value = UserRoleEnum.user

    # If admin did not specify a temporary password, generate one.
    if not temp_password:
        temp_password = token_urlsafe(12)

    if len(temp_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Temporary password must be at least 8 characters")

    hashed = get_password_hash(temp_password)

    import uuid
    user = UserDB(
        id=str(uuid.uuid4()),
        email=email,
        username=username,
        hashed_password=hashed,
        role=role_value,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Admin created user {email} with role {role_value}")

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "role": str(user.role),
            "is_active": getattr(user, "is_active", True),
            "must_change_password": getattr(user, "must_change_password", False),
        },
        "temporary_password": temp_password,
    }


@router.post("/{user_id}/reset-password")
async def admin_reset_password(user_id: str, payload: dict, _: UserResponse = Depends(admin_required), db: Session = Depends(get_db)):
    temp_password = payload.get("temporary_password") or None
    if not temp_password:
        temp_password = token_urlsafe(12)

    if len(temp_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Temporary password must be at least 8 characters")

    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = get_password_hash(temp_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)

    logger.info(f"Admin reset password for user {user.email}")

    return {
        "user_id": user.id,
        "temporary_password": temp_password,
    }


@router.patch("/{user_id}")
async def admin_update_user(user_id: str, payload: dict, _: UserResponse = Depends(admin_required), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_active = payload.get("is_active")
    role_raw = payload.get("role")

    if is_active is not None:
        user.is_active = bool(is_active)

    if role_raw is not None:
        role_str = str(role_raw).lower()
        try:
            if hasattr(UserRoleEnum, role_str):
                user.role = getattr(UserRoleEnum, role_str)
        except Exception:
            pass

    db.commit()
    db.refresh(user)

    logger.info(f"Admin updated user {user.email}")

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": str(user.role),
        "is_active": getattr(user, "is_active", True),
        "must_change_password": getattr(user, "must_change_password", False),
    }