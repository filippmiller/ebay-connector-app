from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta
from app.models.user import UserCreate, UserLogin, UserResponse, Token, PasswordResetRequest, PasswordReset
from app.services.auth import (
    register_user, 
    authenticate_user, 
    create_access_token, 
    get_current_active_user,
    get_password_hash
)
from app.services.database import db
from app.config import settings
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate):
    logger.info(f"Registration attempt for email: {user_data.email}")
    user = register_user(user_data)
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        ebay_connected=user.ebay_connected
    )


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin):
    logger.info(f"Login attempt for email: {user_credentials.email}")
    user = authenticate_user(user_credentials.email, user_credentials.password)
    if not user:
        logger.warning(f"Failed login attempt for: {user_credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    
    logger.info(f"✅ User logged in successfully: {user.email} (role: {user.role})")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_active_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        ebay_connected=current_user.ebay_connected
    )


@router.post("/password-reset/request")
async def request_password_reset(reset_request: PasswordResetRequest):
    logger.info(f"Password reset requested for email: {reset_request.email}")
    user = db.get_user_by_email(reset_request.email)
    
    if not user:
        logger.warning(f"Password reset requested for non-existent email: {reset_request.email}")
        return {"message": "If the email exists, a reset token has been sent"}
    
    reset_token = db.create_password_reset_token(reset_request.email)
    
    logger.info(f"Password reset token created for: {reset_request.email}")
    
    return {
        "message": "If the email exists, a reset token has been sent",
        "reset_token": reset_token
    }


@router.post("/password-reset/confirm")
async def reset_password(reset_data: PasswordReset):
    logger.info(f"Password reset confirmation for email: {reset_data.email}")
    
    email = db.verify_password_reset_token(reset_data.reset_token)
    if not email or email != reset_data.email:
        logger.warning(f"Invalid password reset token used for: {reset_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    user = db.get_user_by_email(reset_data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    hashed_password = get_password_hash(reset_data.new_password)
    db.update_user(user.id, {"hashed_password": hashed_password})
    
    db.delete_password_reset_token(reset_data.reset_token)
    
    logger.info(f"Password reset successful for: {reset_data.email}")
    
    return {"message": "Password reset successful"}
