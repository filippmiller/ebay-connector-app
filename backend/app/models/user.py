from pydantic import BaseModel, EmailStr
from datetime import datetime
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class User(BaseModel):
    id: str
    email: EmailStr
    username: str
    hashed_password: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    # When True, user must change password on next login.
    must_change_password: bool = False
    created_at: datetime
    ebay_connected: bool = False
    ebay_access_token: Optional[str] = None  # Production token
    ebay_refresh_token: Optional[str] = None  # Production refresh token
    ebay_token_expires_at: Optional[datetime] = None  # Production token expires
    ebay_environment: str = "sandbox"
    
    # Sandbox tokens (separate from production)
    ebay_sandbox_access_token: Optional[str] = None
    ebay_sandbox_refresh_token: Optional[str] = None
    ebay_sandbox_token_expires_at: Optional[datetime] = None


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: UserRole = UserRole.USER


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    username: str
    role: UserRole
    is_active: bool
    # When True, the user is forced to change password on next login.
    must_change_password: bool = False
    created_at: datetime
    ebay_connected: bool


class Token(BaseModel):
    access_token: str
    token_type: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    email: EmailStr
    reset_token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str
