from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import timedelta, datetime, timezone
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
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
from app.models_sqlalchemy import get_db
from app.services.security_center import (
    get_or_create_security_settings,
    get_effective_session_ttl_minutes,
    check_pre_login_block,
    record_login_attempt_and_events,
)

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
async def login(
    user_credentials: UserLogin,
    request: Request,
    db_session: Session = Depends(get_db),
):
    rid = getattr(request.state, "rid", "unknown")
    logger.info(f"Login attempt email={user_credentials.email} rid={rid}")

    # Derive basic request context for security logging.
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Use UTC timestamps for all security-related records.
    now = datetime.now(timezone.utc)

    try:
        # Load or create security settings once per request.
        sec_settings = get_or_create_security_settings(db_session)

        # Pre-check for an active block window on this identity+IP.
        is_blocked, block_until = check_pre_login_block(
            db_session,
            email=user_credentials.email,
            ip_address=client_ip,
            now=now,
        )
        if is_blocked:
            # Record a blocked attempt without even checking the password.
            record_login_attempt_and_events(
                db_session,
                email=user_credentials.email,
                user=None,
                ip_address=client_ip,
                user_agent=user_agent,
                success=False,
                reason="blocked",
                settings=sec_settings,
                now=now,
                preblocked=True,
            )
            db_session.commit()

            retry_after = int((block_until - now).total_seconds()) if block_until else None
            headers = {"X-Request-ID": rid}
            if retry_after is not None and retry_after > 0:
                headers["Retry-After"] = str(retry_after)

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please wait before trying again.",
                headers=headers,
            )

        # Perform the actual authentication using the existing database service.
        user = authenticate_user(user_credentials.email, user_credentials.password)
        if not user:
            logger.warning(f"Failed login attempt for: {user_credentials.email} rid={rid}")

            # Record failed attempt and possibly start a new block window.
            record_login_attempt_and_events(
                db_session,
                email=user_credentials.email,
                user=None,
                ip_address=client_ip,
                user_agent=user_agent,
                success=False,
                reason="invalid_credentials",
                settings=sec_settings,
                now=now,
            )
            db_session.commit()

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer", "X-Request-ID": rid},
            )

        # Authentication succeeded: record success and compute effective TTL.
        record_login_attempt_and_events(
            db_session,
            email=user_credentials.email,
            user=None,  # legacy user object is from the old DB; we only log email here.
            ip_address=client_ip,
            user_agent=user_agent,
            success=True,
            reason="ok",
            settings=sec_settings,
            now=now,
        )

        # Determine access-token TTL using security settings as the primary source.
        effective_ttl_minutes = get_effective_session_ttl_minutes(
            sec_settings,
            fallback_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        access_token_expires = timedelta(minutes=effective_ttl_minutes)

        access_token = create_access_token(
            data={"sub": user.id}, expires_delta=access_token_expires
        )

        db_session.commit()

        logger.info(f"✅ User logged in successfully: {user.email} (role: {user.role})")
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException as e:
        # Ensure SQLAlchemy session is not left in a broken state.
        try:
            db_session.rollback()
        except Exception:
            pass
        # Re-raise HTTP exceptions (like 401/429) as-is, but add RID to headers if not present.
        if not getattr(e, "headers", None):
            e.headers = {"X-Request-ID": rid}
        elif "X-Request-ID" not in e.headers:
            e.headers["X-Request-ID"] = rid
        raise
    except SQLAlchemyError as e:
        logger.error(
            f"Database error during login for {user_credentials.email} rid={rid}: {type(e).__name__}: {str(e)}"
        )
        logger.exception("Full database error traceback:")
        try:
            db_session.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
            headers={"X-Request-ID": rid},
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error during login for {user_credentials.email} rid={rid}: {type(e).__name__}: {str(e)}"
        )
        try:
            db_session.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {type(e).__name__}: {str(e)}",
            headers={"X-Request-ID": rid},
        )


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
