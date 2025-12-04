"""Unified eBay Token Provider for all workers.

This module provides a single source of truth for obtaining valid eBay access tokens.
All workers (manual "Run now" and background scheduler) should use this provider
to ensure consistent token handling.

Design goals:
1. Single code path for token retrieval regardless of caller
2. Automatic refresh when token is near expiry
3. Optional validation via Identity API
4. Clear error states that can be logged and surfaced to UI
5. No raw token logging (security)

Usage:
    from app.services.ebay_token_provider import get_valid_access_token

    result = await get_valid_access_token(db, account_id)
    if result.success:
        token = result.access_token
        # Use token for API calls
    else:
        # Handle error: result.error_code, result.error_message
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Literal, Any, Dict

from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy.models import EbayAccount, EbayToken, User
from app.services.ebay_account_service import ebay_account_service
from app.utils.logger import logger


# How many minutes before expiry we should consider refreshing
TOKEN_REFRESH_THRESHOLD_MINUTES = 10

# How long between mandatory Identity API validations (0 = always validate after refresh)
TOKEN_VALIDATION_INTERVAL_MINUTES = 30


@dataclass
class EbayTokenResult:
    """Result of token retrieval from EbayTokenProvider."""
    
    success: bool
    
    # Token data (only populated on success)
    access_token: Optional[str] = None
    environment: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: Optional[List[str]] = None
    
    # Source info
    source: Literal["existing", "refreshed", "none"] = "none"
    token_db_id: Optional[str] = None
    account_id: Optional[str] = None
    ebay_user_id: Optional[str] = None
    
    # Token fingerprint for debugging (SHA256 hash, never raw token)
    token_hash: Optional[str] = None
    
    # Error info (only populated on failure)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Metadata
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses (masks sensitive data)."""
        return {
            "success": self.success,
            "environment": self.environment,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
            "token_db_id": self.token_db_id,
            "account_id": self.account_id,
            "ebay_user_id": self.ebay_user_id,
            "token_hash": self.token_hash,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retrieved_at": self.retrieved_at.isoformat(),
            # Never include raw access_token in API responses
        }


def _compute_token_hash(token: str) -> str:
    """Compute a SHA256 hash of the token for logging/debugging.
    
    This allows us to track which token is being used without exposing the actual token.
    """
    if not token:
        return "empty"
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _get_user_environment(db: Session, account: EbayAccount) -> str:
    """Get the eBay environment for an account based on its owning user."""
    user = db.query(User).filter(User.id == account.org_id).first()
    env = user.ebay_environment if user and user.ebay_environment else settings.EBAY_ENVIRONMENT or "sandbox"
    return env


async def get_valid_access_token(
    db: Session,
    account_id: str,
    *,
    api_family: Optional[str] = None,
    force_refresh: bool = False,
    validate_with_identity_api: bool = False,
    triggered_by: str = "worker",
) -> EbayTokenResult:
    """Get a valid access token for an eBay account.
    
    This is the main entry point for all workers to obtain tokens.
    It ensures consistent token handling across manual and scheduled runs.
    
    Args:
        db: SQLAlchemy session
        account_id: UUID of the EbayAccount
        api_family: Optional API family requesting the token (for logging)
        force_refresh: If True, always refresh even if token is not near expiry
        validate_with_identity_api: If True, validate token via eBay Identity API
        triggered_by: Label for logging (e.g., "manual", "scheduler", "worker")
    
    Returns:
        EbayTokenResult with success=True and access_token, or success=False with error details.
    """
    now = datetime.now(timezone.utc)
    
    # 1. Get the account
    account = ebay_account_service.get_account(db, account_id)
    if not account:
        logger.warning(
            "[token_provider] Account not found: account_id=%s triggered_by=%s",
            account_id, triggered_by,
        )
        return EbayTokenResult(
            success=False,
            account_id=account_id,
            error_code="account_not_found",
            error_message=f"eBay account {account_id} not found",
        )
    
    if not account.is_active:
        logger.warning(
            "[token_provider] Account inactive: account_id=%s triggered_by=%s",
            account_id, triggered_by,
        )
        return EbayTokenResult(
            success=False,
            account_id=account_id,
            ebay_user_id=account.ebay_user_id,
            error_code="account_inactive",
            error_message=f"eBay account {account_id} is inactive",
        )
    
    # 2. Determine environment
    environment = _get_user_environment(db, account)
    
    # 3. Get current token
    token = ebay_account_service.get_token(db, account_id)
    if not token:
        logger.warning(
            "[token_provider] No token found: account_id=%s triggered_by=%s",
            account_id, triggered_by,
        )
        return EbayTokenResult(
            success=False,
            account_id=account_id,
            ebay_user_id=account.ebay_user_id,
            environment=environment,
            error_code="no_token",
            error_message=f"No token exists for account {account_id}",
        )
    
    # 4. Check if token has a refresh error (previously failed)
    if token.refresh_error and not force_refresh:
        logger.warning(
            "[token_provider] Token has refresh error: account_id=%s error=%s triggered_by=%s",
            account_id, token.refresh_error[:100] if token.refresh_error else None, triggered_by,
        )
        # Still try to use the existing token if it's not expired
        # The refresh error might be temporary
    
    # 5. Check token expiry
    token_expires_at = _normalize_datetime(token.expires_at)
    needs_refresh = force_refresh
    
    if not needs_refresh and token_expires_at:
        time_until_expiry = (token_expires_at - now).total_seconds()
        if time_until_expiry < TOKEN_REFRESH_THRESHOLD_MINUTES * 60:
            needs_refresh = True
            logger.info(
                "[token_provider] Token near expiry, needs refresh: account_id=%s expires_in_sec=%d triggered_by=%s",
                account_id, int(time_until_expiry), triggered_by,
            )
    elif not token_expires_at:
        # No expiry info, assume we need to refresh
        needs_refresh = True
    
    # 6. Check if we have an access token at all
    if not token.access_token:
        needs_refresh = True
        logger.warning(
            "[token_provider] Token exists but no access_token: account_id=%s triggered_by=%s",
            account_id, triggered_by,
        )
    
    # 7. Refresh if needed
    source: Literal["existing", "refreshed", "none"] = "existing"
    
    if needs_refresh:
        logger.info(
            "[token_provider] Refreshing token: account_id=%s environment=%s triggered_by=%s api_family=%s",
            account_id, environment, triggered_by, api_family,
        )
        
        refresh_result = await _refresh_token(db, account, token, environment, triggered_by)
        
        if not refresh_result["success"]:
            # Refresh failed - check if we can still use the existing token
            if token.access_token and token_expires_at and token_expires_at > now:
                # Existing token still valid, use it but warn
                logger.warning(
                    "[token_provider] Refresh failed but existing token still valid: account_id=%s error=%s triggered_by=%s",
                    account_id, refresh_result.get("error_message", "unknown")[:100], triggered_by,
                )
            else:
                # No usable token
                return EbayTokenResult(
                    success=False,
                    account_id=account_id,
                    ebay_user_id=account.ebay_user_id,
                    environment=environment,
                    token_db_id=token.id,
                    error_code=refresh_result.get("error_code", "refresh_failed"),
                    error_message=refresh_result.get("error_message", "Token refresh failed"),
                )
        else:
            source = "refreshed"
            # Re-fetch token after refresh
            token = ebay_account_service.get_token(db, account_id)
            token_expires_at = _normalize_datetime(token.expires_at) if token else None
    
    # 8. Final validation and decryption
    if not token:
        return EbayTokenResult(
            success=False,
            account_id=account_id,
            ebay_user_id=account.ebay_user_id,
            environment=environment,
            error_code="no_access_token",
            error_message="No access token available after refresh attempt",
        )
    
    # CRITICAL: Get decrypted access token using the same pattern as _get_plain_refresh_token
    # This ensures we always get a decrypted token, even if property returns ENC:...
    from app.utils import crypto
    
    # Try property first (standard path)
    access_token_value = token.access_token
    
    # DIAGNOSTIC: Log what property returned
    logger.info(
        "[token_provider] Token property returned: account_id=%s triggered_by=%s "
        "token_prefix=%s... is_encrypted=%s",
        account_id, triggered_by,
        access_token_value[:20] if access_token_value else "None",
        "YES" if (access_token_value and access_token_value.startswith("ENC:")) else "NO",
    )
    
    # If property returned encrypted value, try explicit decryption
    if access_token_value and access_token_value.startswith("ENC:"):
        logger.warning(
            "[token_provider] ⚠️ Token property returned ENC:v1:... attempting explicit decryption: "
            "account_id=%s triggered_by=%s token_prefix=%s...",
            account_id, triggered_by, access_token_value[:20],
        )
        # Try to decrypt the raw column directly
        raw_token = token._access_token
        if raw_token:
            decrypted_attempt = crypto.decrypt(raw_token)
            if decrypted_attempt and not decrypted_attempt.startswith("ENC:"):
                access_token_value = decrypted_attempt
                logger.info(
                    "[token_provider] Explicit decryption succeeded: account_id=%s triggered_by=%s",
                    account_id, triggered_by,
                )
            else:
                # Decryption failed - this is a critical error
                logger.error(
                    "[token_provider] ⚠️ TOKEN DECRYPTION FAILED! "
                    "account_id=%s triggered_by=%s. "
                    "Check that SECRET_KEY/JWT_SECRET is correct in worker environment.",
                    account_id, triggered_by,
                )
                return EbayTokenResult(
                    success=False,
                    account_id=account_id,
                    ebay_user_id=account.ebay_user_id,
                    environment=environment,
                    token_db_id=token.id,
                    error_code="decryption_failed",
                    error_message="Token decryption failed - check SECRET_KEY/JWT_SECRET configuration",
                )
        else:
            # No raw token available
            logger.error(
                "[token_provider] No raw access token in DB: account_id=%s triggered_by=%s",
                account_id, triggered_by,
            )
            return EbayTokenResult(
                success=False,
                account_id=account_id,
                ebay_user_id=account.ebay_user_id,
                environment=environment,
                token_db_id=token.id,
                error_code="no_raw_token",
                error_message="No raw access token available in database",
            )
    
    if not access_token_value:
        return EbayTokenResult(
            success=False,
            account_id=account_id,
            ebay_user_id=account.ebay_user_id,
            environment=environment,
            error_code="no_access_token",
            error_message="No access token available after decryption",
        )
    
    # Final validation - token must NOT be encrypted
    if access_token_value.startswith("ENC:"):
        logger.error(
            "[token_provider] ⚠️ TOKEN STILL ENCRYPTED AFTER ALL ATTEMPTS! "
            "account_id=%s triggered_by=%s. This should never happen.",
            account_id, triggered_by,
        )
        return EbayTokenResult(
            success=False,
            account_id=account_id,
            ebay_user_id=account.ebay_user_id,
            environment=environment,
            token_db_id=token.id,
            error_code="token_still_encrypted",
            error_message="Token is still encrypted after decryption attempts - check SECRET_KEY",
        )
    
    # 9. Optional Identity API validation (only with decrypted token)
    if validate_with_identity_api:
        validation_result = await _validate_token_with_identity_api(
            access_token_value, environment, account_id, triggered_by
        )
        if not validation_result["valid"]:
            logger.warning(
                "[token_provider] Identity API validation failed: account_id=%s error=%s triggered_by=%s",
                account_id, validation_result.get("error", "unknown"), triggered_by,
            )
            return EbayTokenResult(
                success=False,
                account_id=account_id,
                ebay_user_id=account.ebay_user_id,
                environment=environment,
                token_db_id=token.id,
                token_hash=_compute_token_hash(access_token_value),
                error_code="identity_validation_failed",
                error_message=validation_result.get("error", "Identity API validation failed"),
            )
    
    # 10. Success!
    token_hash = _compute_token_hash(access_token_value)
    
    logger.info(
        "[token_provider] Token retrieved successfully: account_id=%s environment=%s source=%s "
        "token_hash=%s expires_at=%s triggered_by=%s api_family=%s token_prefix=%s...",
        account_id, environment, source, token_hash,
        token_expires_at.isoformat() if token_expires_at else None,
        triggered_by, api_family,
        access_token_value[:15] if access_token_value else "None",
    )
    
    return EbayTokenResult(
        success=True,
        access_token=access_token_value,  # Use the guaranteed decrypted value
        environment=environment,
        expires_at=token_expires_at,
        scopes=None,  # Could be populated from EbayAuthorization if needed
        source=source,
        token_db_id=token.id,
        account_id=account_id,
        ebay_user_id=account.ebay_user_id,
        token_hash=token_hash,
    )


async def _refresh_token(
    db: Session,
    account: EbayAccount,
    token: EbayToken,
    environment: str,
    triggered_by: str,
) -> Dict[str, Any]:
    """Internal helper to refresh a token.
    
    Returns:
        Dict with keys: success (bool), error_code, error_message
    """
    from app.services.ebay_token_refresh_service import refresh_access_token_for_account
    
    try:
        result = await refresh_access_token_for_account(
            db,
            account,
            triggered_by=f"{triggered_by}_via_provider",
            persist=True,
            capture_http=False,
        )
        
        return {
            "success": result.get("success", False),
            "error_code": result.get("error"),
            "error_message": result.get("error_message"),
        }
    except Exception as e:
        logger.error(
            "[token_provider] Exception during token refresh: account_id=%s error=%s",
            account.id, str(e),
        )
        return {
            "success": False,
            "error_code": "refresh_exception",
            "error_message": str(e),
        }


async def _validate_token_with_identity_api(
    access_token: str,
    environment: str,
    account_id: str,
    triggered_by: str,
) -> Dict[str, Any]:
    """Validate token using eBay Identity API.
    
    Returns:
        Dict with keys: valid (bool), error (str if invalid)
    """
    import httpx
    
    # Determine Identity API URL based on environment
    if environment == "production":
        identity_url = "https://apiz.ebay.com/commerce/identity/v1/user"
    else:
        identity_url = "https://apiz.sandbox.ebay.com/commerce/identity/v1/user"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                identity_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            
            if response.status_code == 200:
                return {"valid": True}
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("errors", [{}])[0].get("message", f"HTTP {response.status_code}")
                logger.warning(
                    "[token_provider] Identity API returned error: account_id=%s status=%d error=%s triggered_by=%s",
                    account_id, response.status_code, error_msg[:100], triggered_by,
                )
                return {"valid": False, "error": error_msg}
                
    except Exception as e:
        logger.error(
            "[token_provider] Identity API call failed: account_id=%s error=%s triggered_by=%s",
            account_id, str(e), triggered_by,
        )
        return {"valid": False, "error": str(e)}


def _normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Convenience alias
get_token = get_valid_access_token

