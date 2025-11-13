from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
import os
from datetime import datetime, timezone

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import SyncLog, EbayAccount, EbayToken, EbayAuthorization
from ..services.auth import admin_required
from ..models.user import User
from ..utils.logger import logger
from ..services.ebay import ebay_service
from ..services.ebay_connect_logger import ebay_connect_logger

FEATURE_TOKEN_INFO = os.getenv('FEATURE_TOKEN_INFO', 'false').lower() == 'true'

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/sync-jobs")
async def get_sync_jobs(
    endpoint: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Get all sync jobs for admin dashboard"""
    query = db.query(SyncLog).filter(SyncLog.user_id == current_user.id)
    
    if endpoint:
        query = query.filter(SyncLog.endpoint == endpoint)
    if status:
        query = query.filter(SyncLog.status == status)
    
    total = query.count()
    jobs = query.order_by(desc(SyncLog.sync_started_at)).offset(offset).limit(limit).all()
    
    return {
        "jobs": [
            {
                "id": j.id,
                "job_id": j.job_id,
                "endpoint": j.endpoint,
                "status": j.status,
                "pages_fetched": j.pages_fetched or 0,
                "records_fetched": j.records_fetched or 0,
                "records_stored": j.records_stored or 0,
                "duration_ms": j.duration_ms or 0,
                "error_text": j.error_text,
                "started_at": j.sync_started_at.isoformat() if j.sync_started_at else None,
                "completed_at": j.sync_completed_at.isoformat() if j.sync_completed_at else None
            }
            for j in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/ebay/tokens/logs")
async def get_ebay_token_logs(
    env: str = Query(..., description="production only"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(admin_required)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    logs = ebay_connect_logger.get_logs(current_user.id, env, limit)
    # Only token-related actions
    filtered = [
        l for l in logs if l.get('action') in (
            'token_refreshed', 'token_refresh_failed', 'token_info_viewed', 'token_call_blocked_missing_scopes'
        )
    ]
    return {"logs": filtered}


@router.post("/ebay/tokens/logs/blocked-scope")
async def log_blocked_scope(
    env: str = Query(..., description="production only"),
    details: dict = None,
    current_user: User = Depends(admin_required)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")
    try:
        ebay_connect_logger.log_event(
            user_id=current_user.id,
            environment=env,
            action="token_call_blocked_missing_scopes",
            request={"method": "POST", "url": "/api/admin/ebay/tokens/logs/blocked-scope", "body": details},
            response={"status": 200}
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to log blocked scope: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="log_failed")


@router.get("/ebay/tokens/info")
async def get_ebay_tokens_info(
    env: str = Query(..., description="production only"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    # Pick the first active account for this org (user)
    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.org_id == current_user.id,
        EbayAccount.is_active == True
    ).order_by(EbayAccount.connected_at.desc()).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_account")

    token: Optional[EbayToken] = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).first()
    auth: Optional[EbayAuthorization] = db.query(EbayAuthorization).filter(EbayAuthorization.ebay_account_id == account.id).first()

    now = datetime.now(timezone.utc)

    def mask(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        if len(val) <= 12:
            return "****"
        return f"{val[:6]}...{val[-6:]}"

    access_expires_at = token.expires_at if token and token.expires_at else None
    access_ttl_sec = int((access_expires_at - now).total_seconds()) if access_expires_at else None
    refresh_expires_at = token.refresh_expires_at if token and token.refresh_expires_at else None
    refresh_ttl_sec = int((refresh_expires_at - now).total_seconds()) if refresh_expires_at else None

    # Log view (no secrets)
    try:
        ebay_connect_logger.log_event(
            user_id=current_user.id,
            environment=env,
            action="token_info_viewed",
            request={"method": "GET", "url": f"/api/admin/ebay/tokens/info?env={env}"}
        )
    except Exception:
        pass

    return {
        "now_utc": now.isoformat(),
        "source": "user",
        "ebay_account": {
            "id": account.id,
            "username": account.username,
            "ebay_user_id": account.ebay_user_id,
        },
        "access_token_masked": mask(token.access_token if token else None),
        "access_expires_at": access_expires_at.isoformat() if access_expires_at else None,
        "access_ttl_sec": access_ttl_sec,
        "refresh_token_masked": mask(token.refresh_token if token else None),
        "refresh_expires_at": refresh_expires_at.isoformat() if refresh_expires_at else None,
        "refresh_ttl_sec": refresh_ttl_sec,
        "scopes": (auth.scopes if auth and auth.scopes else []),
    }


@router.post("/ebay/tokens/refresh")
async def refresh_ebay_access_token(
    env: str = Query(..., description="production only"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.org_id == current_user.id,
        EbayAccount.is_active == True
    ).order_by(EbayAccount.connected_at.desc()).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_account")

    token: Optional[EbayToken] = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).first()
    if not token or not token.refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_refresh_token")

    # Execute refresh
    try:
        from datetime import timezone, timedelta
        new_resp = await ebay_service.refresh_access_token(token.refresh_token)
        # Update storage (access token only; refresh token remains long-lived)
        token.access_token = new_resp.access_token
        token.expires_at = datetime.now(timezone.utc) + (timedelta(seconds=new_resp.expires_in) if getattr(new_resp, 'expires_in', None) else timedelta(seconds=0))
        token.last_refreshed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(token)
        # Log success (no secrets)
        try:
            ebay_connect_logger.log_event(
                user_id=current_user.id,
                environment=env,
                action="token_refreshed",
                request={"method": "POST", "url": f"/api/admin/ebay/tokens/refresh?env={env}"},
                response={"status": 200, "body": {"access_expires_at": token.expires_at.isoformat() if token.expires_at else None}}
            )
        except Exception:
            pass
        logger.info(f"Admin token refresh for account {account.id}")
    except Exception as e:
        try:
            ebay_connect_logger.log_event(
                user_id=current_user.id,
                environment=env,
                action="token_refresh_failed",
                request={"method": "POST", "url": f"/api/admin/ebay/tokens/refresh?env={env}"},
                error=str(e)
            )
        except Exception:
            pass
        logger.error(f"Admin token refresh failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="refresh_failed")

    now = datetime.now(timezone.utc)
    access_expires_at = token.expires_at if token.expires_at else None
    ttl_sec = int((access_expires_at - now).total_seconds()) if access_expires_at else None

    return {
        "access_expires_at": access_expires_at.isoformat() if access_expires_at else None,
        "access_ttl_sec": ttl_sec,
    }
