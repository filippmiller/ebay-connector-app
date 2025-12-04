"""
Unified eBay Access Token Fetcher - Single Source of Truth

This module provides a single function that ALL workers must use to obtain
eBay access tokens. It guarantees that tokens are always decrypted and never
returned in ENC:v1:... format.

CRITICAL: All workers (Orders, Transactions, Returns, Messages, etc.) must
use fetch_active_ebay_token() instead of directly accessing token.access_token
or any encrypted fields.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay_token_provider import get_valid_access_token
from app.utils.logger import logger


def _compute_token_hash(token: str) -> str:
    """Compute a short hash of the token for logging (never log full token)."""
    if not token:
        return "empty"
    return hashlib.sha256(token.encode()).hexdigest()[:12]


async def fetch_active_ebay_token(
    db: Session,
    ebay_account_id: str,
    *,
    triggered_by: str = "unknown",
    api_family: Optional[str] = None,
) -> Optional[str]:
    """
    Fetch and return a usable eBay access token for the given account.
    
    This is the SINGLE SOURCE OF TRUTH for all workers to obtain tokens.
    It guarantees:
    - Token is always decrypted (never returns ENC:v1:...)
    - Token is validated and refreshed if needed
    - Proper logging with mode, account_id, token_hash
    
    Args:
        db: SQLAlchemy session
        ebay_account_id: UUID of the eBay account
        triggered_by: How this was triggered ("manual", "scheduler", "internal_scheduler", etc.)
        api_family: Optional API family label for logging (e.g., "orders", "transactions")
    
    Returns:
        Decrypted access token string (v^1.1#...) or None if token unavailable
        
    Raises:
        None - returns None on any error (caller should handle)
    """
    # Use the unified token provider which handles decryption correctly
    token_result = await get_valid_access_token(
        db,
        ebay_account_id,
        api_family=api_family,
        force_refresh=False,
        validate_with_identity_api=False,
        triggered_by=f"fetcher_{triggered_by}",
    )
    
    if not token_result.success:
        logger.warning(
            "[fetch_active_ebay_token] Token retrieval failed: account_id=%s "
            "error_code=%s error_message=%s triggered_by=%s api_family=%s",
            ebay_account_id,
            token_result.error_code,
            token_result.error_message,
            triggered_by,
            api_family,
        )
        return None
    
    decrypted_token = token_result.access_token
    if not decrypted_token:
        logger.warning(
            "[fetch_active_ebay_token] No access token in result: account_id=%s triggered_by=%s",
            ebay_account_id, triggered_by,
        )
        return None
    
    # CRITICAL VALIDATION: Token must NOT be encrypted
    if decrypted_token.startswith("ENC:"):
        logger.error(
            "[fetch_active_ebay_token] ⚠️ TOKEN STILL ENCRYPTED! "
            "account_id=%s token_hash=%s triggered_by=%s api_family=%s. "
            "This indicates decryption failure - check SECRET_KEY/JWT_SECRET in environment.",
            ebay_account_id,
            token_result.token_hash,
            triggered_by,
            api_family,
        )
        return None
    
    # Log successful token retrieval
    token_hash = _compute_token_hash(decrypted_token)
    logger.info(
        "[fetch_active_ebay_token] ✅ Token retrieved successfully: account_id=%s "
        "token_hash=%s source=%s environment=%s triggered_by=%s api_family=%s "
        "token_prefix=%s... token_is_decrypted=YES",
        ebay_account_id,
        token_hash,
        token_result.source,
        token_result.environment,
        triggered_by,
        api_family,
        decrypted_token[:15] if decrypted_token else "None",
    )
    
    return decrypted_token


# Convenience function that creates its own DB session
async def fetch_active_ebay_token_with_session(
    ebay_account_id: str,
    *,
    triggered_by: str = "unknown",
    api_family: Optional[str] = None,
) -> Optional[str]:
    """
    Convenience wrapper that creates its own DB session.
    
    Use this when you don't have a DB session available.
    For workers that already have a session, use fetch_active_ebay_token() directly.
    """
    db = SessionLocal()
    try:
        return await fetch_active_ebay_token(
            db,
            ebay_account_id,
            triggered_by=triggered_by,
            api_family=api_family,
        )
    finally:
        db.close()

