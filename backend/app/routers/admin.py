from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from typing import Optional, Any
import os
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import SyncLog, EbayAccount, EbayToken, EbayAuthorization, EbayScopeDefinition, EbayEvent
from ..models_sqlalchemy.ebay_workers import (
    EbayWorkerRun,
    BackgroundWorker,
    EbayTokenRefreshLog,
)
from ..services.auth import admin_required
from ..models.user import User
from ..utils.logger import logger
from ..services.ebay import ebay_service
from ..services.ebay_connect_logger import ebay_connect_logger
from ..services.ebay_notification_topics import SUPPORTED_TOPICS, PRIMARY_WEBHOOK_TOPIC_ID
from ..config import settings

FEATURE_TOKEN_INFO = os.getenv('FEATURE_TOKEN_INFO', 'false').lower() == 'true'

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TokenRefreshDebugRequest(BaseModel):
    """Request body for /ebay/token/refresh-debug.

    We keep this minimal on purpose: the endpoint derives everything else from
    the account + DB state so that it always uses the same refresh token and
    environment as the background worker.
    """

    ebay_account_id: str


@router.get("/notifications/status")
async def get_notifications_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Public wrapper for notifications status that never raises.

    Any internal error is converted into an ``ok=False`` response with an
    appropriate ``state`` and ``errorSummary`` so the UI never sees a raw 500.
    """

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL
    checked_at = datetime.now(timezone.utc).isoformat()

    try:
        # Delegate to the core implementation which already handles most
        # Notification API and configuration errors in a structured way.
        return await _get_notifications_status_inner(current_user=current_user, db=db)
    except HTTPException as http_exc:
        # Do not propagate HTTPException status codes to the client; always
        # respond with HTTP 200 and a clear diagnostic payload.
        logger.warning(
            "Notifications status HTTPException in wrapper: %s",
            getattr(http_exc, "detail", http_exc),
        )
        detail = getattr(http_exc, "detail", None)
        message = str(detail) if detail else "Notification API error"
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "notification_api_error",
            "reason": message,
            "errorSummary": f"notification_api_error: {message}",
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "destinationStatus": None,
            "subscriptionStatus": None,
            "verificationStatus": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": None,
            "topics": [],
        }
    except Exception as exc:  # pragma: no cover - last-resort safety net
        logger.exception("Unexpected error in /api/admin/notifications/status wrapper")
        message = str(exc)
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "internal_error",
            "reason": message,
            "errorSummary": f"internal_error: {type(exc).__name__}: {message}",
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "destinationStatus": None,
            "subscriptionStatus": None,
            "verificationStatus": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": None,
            "topics": [],
        }

@router.post("/cases/sync")
async def admin_run_cases_sync_for_account(
    account_id: str = Query(..., description="eBay account id"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Run the Post-Order cases worker once for an account (admin-only).

    This wraps ``run_cases_worker_for_account`` so admins can trigger a cases
    sync directly from the Admin area and immediately see the resulting
    worker-run summary, including normalization statistics.
    """

    # Ensure the account belongs to the current org.
    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    # Import here to avoid circular imports at module load time.
    from app.services.ebay_workers.cases_worker import run_cases_worker_for_account

    run_id = await run_cases_worker_for_account(account_id)
    if not run_id:
        # Worker may be disabled or a run lock could not be acquired.
        return {"status": "skipped", "reason": "not_started"}

    worker_run: Optional[EbayWorkerRun] = db.query(EbayWorkerRun).filter(EbayWorkerRun.id == run_id).first()
    if not worker_run:
        return {"status": "started", "run_id": run_id, "summary": None}

    return {
        "status": worker_run.status,
        "run_id": worker_run.id,
        "api_family": worker_run.api_family,
        "started_at": worker_run.started_at.isoformat() if worker_run.started_at else None,
        "finished_at": worker_run.finished_at.isoformat() if worker_run.finished_at else None,
        "summary": worker_run.summary_json or {},
    }


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


@router.get("/ebay/tokens/status")
async def get_ebay_token_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return per-account token status for the current org.

    This aggregates information from ebay_accounts, ebay_tokens and the
    ebay_token_refresh_log table so the Admin UI can quickly see which
    accounts are healthy, expiring soon, expired, or in error.
    """

    now_utc = datetime.now(timezone.utc)

    accounts = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id)
        .order_by(desc(EbayAccount.connected_at))
        .all()
    )

    def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    results = []
    for account in accounts:
        token: Optional[EbayToken] = (
            db.query(EbayToken)
            .filter(EbayToken.ebay_account_id == account.id)
            .order_by(desc(EbayToken.updated_at))
            .first()
        )

        expires_at_utc: Optional[datetime] = (
            _to_utc(token.expires_at) if token and token.expires_at else None
        )
        expires_in_seconds: Optional[int]
        if expires_at_utc is not None:
            expires_in_seconds = int((expires_at_utc - now_utc).total_seconds())
        else:
            expires_in_seconds = None

        has_refresh_token = bool(token and token.refresh_token)
        refresh_error = getattr(token, "refresh_error", None) if token else None

        # Latest refresh attempt for this account
        last_log: Optional[EbayTokenRefreshLog] = (
            db.query(EbayTokenRefreshLog)
            .filter(EbayTokenRefreshLog.ebay_account_id == account.id)
            .order_by(EbayTokenRefreshLog.started_at.desc())
            .first()
        )
        last_refresh_at: Optional[datetime] = None
        last_refresh_success: Optional[bool] = None
        last_refresh_error: Optional[str] = None

        if last_log is not None:
            last_refresh_at = last_log.finished_at or last_log.started_at
            last_refresh_success = last_log.success
            if not last_log.success:
                last_refresh_error = last_log.error_message

        # Count consecutive failures from the most recent logs (up to 10) so we
        # can surface "3 failures in a row"-style hints in the UI.
        recent_logs = (
            db.query(EbayTokenRefreshLog)
            .filter(EbayTokenRefreshLog.ebay_account_id == account.id)
            .order_by(EbayTokenRefreshLog.started_at.desc())
            .limit(10)
            .all()
        )
        failures_in_row = 0
        for log_row in recent_logs:
            if log_row.success:
                break
            failures_in_row += 1

        # Derive high-level status
        if token is None:
            status = "not_connected"
        else:
            if refresh_error:
                status = "error"
            elif expires_at_utc is None:
                status = "unknown"
            else:
                if expires_in_seconds is not None and expires_in_seconds <= 0:
                    status = "expired"
                elif (
                    expires_in_seconds is not None
                    and expires_in_seconds <= 600  # 10 minutes
                ):
                    status = "expiring_soon"
                else:
                    status = "ok"

        results.append(
            {
                "account_id": account.id,
                "account_name": account.house_name,
                "ebay_user_id": account.ebay_user_id,
                "status": status,
                "expires_at": expires_at_utc.isoformat() if expires_at_utc else None,
                "expires_in_seconds": expires_in_seconds,
                "has_refresh_token": has_refresh_token,
                "last_refresh_at": last_refresh_at.isoformat()
                if last_refresh_at
                else None,
                "last_refresh_success": last_refresh_success,
                "last_refresh_error": last_refresh_error,
                "refresh_failures_in_row": failures_in_row,
            }
        )

    return {"accounts": results}


@router.get("/workers/token-refresh/status")
async def get_token_refresh_worker_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return heartbeat/status information for the token refresh worker."""

    # BackgroundWorker is global, not per-org, but we still require admin auth.
    worker: Optional[BackgroundWorker] = (
        db.query(BackgroundWorker)
        .filter(BackgroundWorker.worker_name == "token_refresh_worker")
        .one_or_none()
    )
    if worker is None:
        return {
            "worker_name": "token_refresh_worker",
            "interval_seconds": 600,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error_message": None,
            "runs_ok_in_row": 0,
            "runs_error_in_row": 0,
            "next_run_estimated_at": None,
        }

    interval = worker.interval_seconds or 600
    ref_time: Optional[datetime] = worker.last_started_at or worker.last_finished_at
    next_run_estimated_at: Optional[str] = None
    if ref_time is not None and interval:
        try:
            next_dt = ref_time + timedelta(seconds=interval)
            next_run_estimated_at = next_dt.astimezone(timezone.utc).isoformat()
        except Exception:  # pragma: no cover - defensive
            next_run_estimated_at = None

    return {
        "worker_name": worker.worker_name,
        "interval_seconds": interval,
        "last_started_at": worker.last_started_at.isoformat()
        if worker.last_started_at
        else None,
        "last_finished_at": worker.last_finished_at.isoformat()
        if worker.last_finished_at
        else None,
        "last_status": worker.last_status,
        "last_error_message": worker.last_error_message,
        "runs_ok_in_row": worker.runs_ok_in_row,
        "runs_error_in_row": worker.runs_error_in_row,
        "next_run_estimated_at": next_run_estimated_at,
    }


@router.get("/ebay/tokens/refresh/log")
async def get_ebay_token_refresh_log(
    account_id: str = Query(..., description="eBay account id"),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return recent token refresh attempts for a single eBay account."""

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    logs = (
        db.query(EbayTokenRefreshLog)
        .filter(EbayTokenRefreshLog.ebay_account_id == account_id)
        .order_by(EbayTokenRefreshLog.started_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "account": {
            "id": account.id,
            "ebay_user_id": account.ebay_user_id,
            "house_name": account.house_name,
        },
        "logs": [
            {
                "id": row.id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "success": row.success,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "old_expires_at": row.old_expires_at.isoformat()
                if row.old_expires_at
                else None,
                "new_expires_at": row.new_expires_at.isoformat()
                if row.new_expires_at
                else None,
                "triggered_by": row.triggered_by,
            }
            for row in logs
        ],
    }


@router.post("/ebay/token/refresh-debug")
async def debug_refresh_ebay_token(
    payload: TokenRefreshDebugRequest,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Run a one-off token refresh for an account and capture raw HTTP.

    This uses the same request-building logic as the background token refresh
    worker but *does not* write secrets to normal logs. Instead it returns a
    structured payload with the exact HTTP request and response so the admin
    UI can display it in a terminal-like view.
    """

    account_id = payload.ebay_account_id

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(EbayToken.updated_at.desc())
        .first()
    )

    env = settings.EBAY_ENVIRONMENT or "sandbox"

    if not token or not token.refresh_token:
        # Nothing to call eBay with; return a structured error without making
        # any external HTTP requests.
        return {
            "account": {
                "id": account.id,
                "ebay_user_id": account.ebay_user_id,
                "house_name": account.house_name,
            },
            "environment": env,
            "success": False,
            "error": "no_refresh_token",
            "error_description": "Account has no refresh token stored",
            "request": None,
            "response": None,
        }

    debug_payload = await ebay_service.debug_refresh_access_token_http(
        token.refresh_token,
        environment=env,
    )

    # Attach basic account context; the rest of the shape comes from the
    # shared debug_refresh_access_token_http helper.
    return {
        "account": {
            "id": account.id,
            "ebay_user_id": account.ebay_user_id,
            "house_name": account.house_name,
        },
        **debug_payload,
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


@router.get("/ebay/connect/last")
async def get_last_connect_cycle(
    env: str = Query(..., description="sandbox or production"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Return the most recent connect cycle summary: start_auth, callback, exchange, connect_success, plus current tokens/authorizations."""
    # Logs
    from ..services.database import db as db_svc
    logs = db_svc.get_connect_logs(current_user.id, env, limit)
    summary = {}
    for entry in logs:
        act = entry.get('action')
        if act and act not in summary:
            if act in ("start_auth", "callback_received", "exchange_code_for_token", "connect_success", "token_exchange_request", "token_exchange_response"):
                summary[act] = entry
        if len(summary) >= 4:
            # we captured key stages
            pass
    # Account snapshot
    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.org_id == current_user.id,
        EbayAccount.is_active == True
    ).order_by(desc(EbayAccount.connected_at)).first()
    token = None
    auth = None
    if account:
        token = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).order_by(desc(EbayToken.updated_at)).first()
        auth = db.query(EbayAuthorization).filter(EbayAuthorization.ebay_account_id == account.id).first()
    return {
        "logs": summary,
        "account": {
            "id": (account.id if account else None),
            "username": (account.username if account else None),
            "ebay_user_id": (account.ebay_user_id if account else None),
        },
        "token": {
            "access_len": (len(token.access_token) if token and token.access_token else 0),
            "access_expires_at": (token.expires_at.isoformat() if token and token.expires_at else None),
            "refresh_len": (len(token.refresh_token) if token and token.refresh_token else 0),
            "refresh_expires_at": (token.refresh_expires_at.isoformat() if token and token.refresh_expires_at else None),
        } if token else None,
        "authorizations": {
            "scopes": (auth.scopes if auth and auth.scopes else []),
            "count": (len(auth.scopes) if auth and auth.scopes else 0),
        }
    }

@router.get("/ebay/accounts/scopes")
async def get_ebay_accounts_scopes(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Return eBay accounts for this org with their stored scopes vs scope catalog.

    This is an admin-only view that shows:
    - scope_catalog: all active user/both scopes from ebay_scope_definitions
    - accounts: each EbayAccount + its authorizations.scopes and whether it has full catalog
    """
    # Load catalog of available scopes (user-consent and both)
    catalog_rows = (
        db.query(EbayScopeDefinition)
        .filter(
            EbayScopeDefinition.is_active == True,  # noqa: E712
            EbayScopeDefinition.grant_type.in_(['user', 'both']),
        )
        .order_by(EbayScopeDefinition.scope)
        .all()
    )
    catalog_scopes = [r.scope for r in catalog_rows]

    # All accounts for current org (including inactive, so admin sees history)
    accounts = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id)
        .order_by(desc(EbayAccount.connected_at))
        .all()
    )

    result_accounts = []
    for account in accounts:
        # All authorizations for this account
        auth_rows = (
            db.query(EbayAuthorization)
            .filter(EbayAuthorization.ebay_account_id == account.id)
            .order_by(EbayAuthorization.created_at.desc())
            .all()
        )
        scopes: list[str] = []
        for auth in auth_rows:
            if auth.scopes:
                scopes.extend(auth.scopes)
        # Unique + sorted scopes
        unique_scopes = sorted(set(scopes))
        missing_catalog_scopes = [s for s in catalog_scopes if s not in unique_scopes]
        has_all_catalog_scopes = bool(catalog_scopes) and not missing_catalog_scopes

        # Latest token snapshot (if exists) – minimal info only
        token = (
            db.query(EbayToken)
            .filter(EbayToken.ebay_account_id == account.id)
            .order_by(desc(EbayToken.updated_at))
            .first()
        )

        result_accounts.append({
            "id": account.id,
            "username": account.username,
            "ebay_user_id": account.ebay_user_id,
            "house_name": account.house_name,
            "is_active": account.is_active,
            "connected_at": account.connected_at.isoformat() if account.connected_at else None,
            "scopes": unique_scopes,
            "scopes_count": len(unique_scopes),
            "has_all_catalog_scopes": has_all_catalog_scopes,
            "missing_catalog_scopes": missing_catalog_scopes,
            "token": {
                "access_expires_at": token.expires_at.isoformat() if token and token.expires_at else None,
                "has_refresh_token": bool(token and token.refresh_token),
            } if token else None,
        })

    return {
        "scope_catalog": [
            {
                "scope": r.scope,
                "grant_type": r.grant_type,
                "description": r.description,
            }
            for r in catalog_rows
        ],
        "accounts": result_accounts,
    }


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

    token: Optional[EbayToken] = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).order_by(EbayToken.updated_at.desc()).first()
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
            request={"method": "GET", "url": f"/api/admin/ebay/tokens/info?env={env}"},
            response={
                "status": 200,
                "body": {
                    "meta": {
                        "ebay_account_id": str(account.id),
                        "ebay_username": account.username,
                        "access_len": (len(token.access_token) if token and token.access_token else 0),
                        "refresh_len": (len(token.refresh_token) if token and token.refresh_token else 0)
                    }
                }
            }
        )
    except Exception:
        pass

    return {
        "now_utc": now.isoformat(),
        "source": "account_level",
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
        # If eBay rotated refresh token or returned its TTL, persist it
        if getattr(new_resp, 'refresh_token', None):
            token.refresh_token = new_resp.refresh_token
        if getattr(new_resp, 'refresh_token_expires_in', None):
            token.refresh_expires_at = datetime.now(timezone.utc) + timedelta(seconds=getattr(new_resp, 'refresh_token_expires_in'))
        db.commit()
        db.refresh(token)
        # Log success (no secrets)
        try:
            ebay_connect_logger.log_event(
                user_id=current_user.id,
                environment=env,
                action="token_refreshed",
                request={"method": "POST", "url": f"/api/admin/ebay/tokens/refresh?env={env}"},
                response={
                    "status": 200,
                    "body": {
                        "meta": {
                            "ebay_account_id": str(account.id),
                            "ebay_username": account.username,
                            "access_len": (len(token.access_token) if token and token.access_token else 0),
                            "refresh_len": (len(token.refresh_token) if token and token.refresh_token else 0),
                            "access_expires_at": token.expires_at.isoformat() if token.expires_at else None,
                            "refresh_expires_at": token.refresh_expires_at.isoformat() if token.refresh_expires_at else None
                        }
                    }
                }
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


@router.get("/ebay-events")
async def list_ebay_events(
    topic: Optional[str] = Query(None, description="Exact topic or comma-separated list of topics"),
    entity_type: Optional[str] = Query(None, alias="entityType"),
    entity_id: Optional[str] = Query(None, alias="entityId"),
    ebay_account: Optional[str] = Query(None, alias="ebayAccount"),
    source: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_ts: Optional[str] = Query(None, alias="from", description="ISO timestamp lower bound"),
    to_ts: Optional[str] = Query(None, alias="to", description="ISO timestamp upper bound"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None, alias="sortBy", description="event_time or created_at"),
    sort_dir: str = Query("desc", alias="sortDir", description="asc or desc"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """List eBay events for the admin Notifications UI.

    Filtering is intentionally simple for the first version and can be
    extended as we add processors and more metadata.
    """

    query = db.query(EbayEvent)

    if topic:
        topics = [t.strip() for t in topic.split(",") if t.strip()]
        if topics:
            if len(topics) == 1:
                query = query.filter(EbayEvent.topic == topics[0])
            else:
                query = query.filter(EbayEvent.topic.in_(topics))

    if entity_type:
        query = query.filter(EbayEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(EbayEvent.entity_id == entity_id)
    if ebay_account:
        query = query.filter(EbayEvent.ebay_account == ebay_account)
    if source:
        query = query.filter(EbayEvent.source == source)
    if channel:
        query = query.filter(EbayEvent.channel == channel)
    if status:
        query = query.filter(EbayEvent.status == status)

    def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            if ts.endswith("Z"):
                ts_local = ts.replace("Z", "+00:00")
            else:
                ts_local = ts
            return datetime.fromisoformat(ts_local)
        except Exception:
            return None

    from_dt = _parse_iso(from_ts)
    to_dt = _parse_iso(to_ts)

    if from_dt:
        query = query.filter(
            or_(
                and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time >= from_dt),
                and_(EbayEvent.event_time.is_(None), EbayEvent.created_at >= from_dt),
            )
        )

    if to_dt:
        query = query.filter(
            or_(
                and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time <= to_dt),
                and_(EbayEvent.event_time.is_(None), EbayEvent.created_at <= to_dt),
            )
        )

    total = query.count()

    # Sorting
    effective_sort_by = (sort_by or "event_time").lower()
    if effective_sort_by not in ("event_time", "created_at"):
        effective_sort_by = "event_time"

    sort_field = EbayEvent.event_time if effective_sort_by == "event_time" else EbayEvent.created_at
    if (sort_dir or "desc").lower() == "asc":
        query = query.order_by(sort_field.asc())
    else:
        query = query.order_by(sort_field.desc())

    events = query.offset(offset).limit(limit).all()

    items = []
    for ev in events:
        payload = ev.payload or {}
        payload_preview: Any

        if isinstance(payload, dict):
            # Prefer Notification API-style preview when available.
            preferred_keys = ["metadata", "notification"]
            preview = {k: payload.get(k) for k in preferred_keys if k in payload}

            if not preview:
                # Fallback: shallow preview of a few top-level keys.
                preview = {}
                for idx, (k, v) in enumerate(payload.items()):
                    preview[k] = v
                    if idx >= 4:
                        break
            payload_preview = preview
        else:
            payload_preview = payload

        items.append(
            {
                "id": str(ev.id),
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
                "source": ev.source,
                "channel": ev.channel,
                "topic": ev.topic,
                "entity_type": ev.entity_type,
                "entity_id": ev.entity_id,
                "ebay_account": ev.ebay_account,
                "event_time": ev.event_time.isoformat() if ev.event_time else None,
                "publish_time": ev.publish_time.isoformat() if ev.publish_time else None,
                "status": ev.status,
                "error": ev.error,
                "signature_valid": ev.signature_valid,
                "signature_kid": ev.signature_kid,
                "payload_preview": payload_preview,
            }
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/ebay-events/{event_id}")
async def get_ebay_event_detail(
    event_id: str,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return full details (including headers+payload) for a single ebay_events row."""

    ev: Optional[EbayEvent] = db.query(EbayEvent).filter(EbayEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    return {
        "id": str(ev.id),
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
        "source": ev.source,
        "channel": ev.channel,
        "topic": ev.topic,
        "entity_type": ev.entity_type,
        "entity_id": ev.entity_id,
        "ebay_account": ev.ebay_account,
        "event_time": ev.event_time.isoformat() if ev.event_time else None,
        "publish_time": ev.publish_time.isoformat() if ev.publish_time else None,
        "status": ev.status,
        "error": ev.error,
        "signature_valid": ev.signature_valid,
        "signature_kid": ev.signature_kid,
        "headers": ev.headers or {},
        "payload": ev.payload,
    }


# Internal helper implementing the core notifications status logic.
# The public route wrapper `get_notifications_status` below delegates to this
# helper and adds a final catch-all for robustness.
async def _get_notifications_status_inner(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return high-level health for the Notifications Center webhook.

    Status is derived from Notification API destination/subscription state and
    the presence of recent events for the primary webhook topic.

    This handler should *not* raise uncaught exceptions for normal
    misconfigurations or Notification API errors. Instead, it always returns
    HTTP 200 with an `ok` flag and structured error information.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL
    checked_at = datetime.now(timezone.utc).isoformat()

    def _build_topics_payload_for_error(error_reason: str, error_summary: str | None) -> list[dict]:
        """Best-effort per-topic diagnostics when Notification API calls fail.

        We still include recent event counts from the local database so the
        UI can show whether events have ever flowed for a topic.
        """

        topics_payload: list[dict] = []
        now_local = datetime.now(timezone.utc)
        window_start_local = now_local - timedelta(hours=24)

        for topic_cfg in SUPPORTED_TOPICS:
            topic_id = topic_cfg.topic_id
            recent_count = 0
            last_event_time: str | None = None

            try:
                topic_recent_q = db.query(EbayEvent).filter(EbayEvent.topic == topic_id)
                topic_recent_q = topic_recent_q.filter(
                    or_(
                        and_(
                            EbayEvent.event_time.isnot(None),
                            EbayEvent.event_time >= window_start_local,
                        ),
                        and_(
                            EbayEvent.event_time.is_(None),
                            EbayEvent.created_at >= window_start_local,
                        ),
                    )
                )
                recent_count = topic_recent_q.count()

                topic_latest = (
                    db.query(EbayEvent)
                    .filter(EbayEvent.topic == topic_id)
                    .order_by(
                        EbayEvent.event_time.desc().nullslast(),
                        EbayEvent.created_at.desc(),
                    )
                    .first()
                )
                if topic_latest:
                    base_ts = topic_latest.event_time or topic_latest.created_at
                    last_event_time = base_ts.isoformat() if base_ts else None
            except Exception:
                # DB diagnostics are best-effort; ignore failures here so we
                # still return structured status instead of HTTP 500.
                pass

            topics_payload.append(
                {
                    "topicId": topic_id,
                    "scope": None,
                    "destinationId": None,
                    "subscriptionId": None,
                    "destinationStatus": None,
                    "subscriptionStatus": None,
                    "verificationStatus": None,
                    "tokenType": None,
                    "status": "ERROR",
                    "error": error_summary or error_reason,
                    "recentEvents": {
                        "count": recent_count,
                        "lastEventTime": last_event_time,
                    },
                }
            )

        return topics_payload

    if not endpoint_url:
        error_summary = "EBAY_NOTIFICATION_DESTINATION_URL is not configured on the backend."
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": None,
            "state": "misconfigured",
            "reason": "missing_destination_url",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "topics": [],
        }

    # Pick first active account for this org
    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        error_summary = "No active eBay account found for this organization. Connect an account first."
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "no_account",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": None,
            "topics": [],
        }

    account_info = {
        "id": str(account.id),
        "username": account.username or account.ebay_user_id,
        "environment": env,
    }

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        error_summary = (
            "No eBay access token found for the active account; reconnect eBay "
            "for this organization."
        )
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "no_access_token",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": account_info,
            "topics": [],
        }

    access_token = token.access_token

    # Primary topic used for overall webhook health (currently MARKETPLACE_ACCOUNT_DELETION).
    primary_topic_id = PRIMARY_WEBHOOK_TOPIC_ID

    try:
        dest, sub = await ebay_service.get_notification_status(
            access_token,
            endpoint_url,
            primary_topic_id,
        )
    except HTTPException as exc:
        # Surface Notification API error as misconfigured state with structured payload for UI diagnostics.
        logger.error(
            "Notification status check failed via Notification API: status=%s detail=%s",
            exc.status_code,
            exc.detail,
        )
        detail = exc.detail
        if isinstance(detail, dict):
            nerr = {
                "status_code": detail.get("status_code", exc.status_code),
                "message": detail.get("message") or str(detail),
                "body": detail.get("body"),
            }
        else:
            nerr = {"status_code": exc.status_code, "message": str(detail)}

        # Try to detect explicit challenge verification failures (195020) so we
        # can surface a clearer reason in Diagnostics.
        reason = "notification_api_error"
        body_obj = nerr.get("body")
        if isinstance(body_obj, dict):
            try:
                errors = body_obj.get("errors") or []
                for err in errors:
                    if isinstance(err, dict) and err.get("errorId") == 195020:
                        reason = "verification_failed"
                        break
            except Exception:
                # Best-effort only; fall back to generic reason if parsing fails.
                pass

        body_preview = body_obj
        if isinstance(body_preview, (dict, list)):
            body_preview = str(body_preview)[:300]
        error_summary = f"Notification API HTTP {nerr.get('status_code')} - {nerr.get('message')}"
        if body_preview:
            error_summary += f" | body: {body_preview}"

        topics_payload = _build_topics_payload_for_error(reason, error_summary)

        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": reason,
            "notificationError": nerr,
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": account_info,
            "topics": topics_payload,
        }
    except Exception as exc:  # pragma: no cover - defensive; should be rare
        logger.exception(
            "Unexpected error while checking Notification API status for primary topic %s",
            primary_topic_id,
        )
        error_summary = f"Unexpected error while checking Notification API status: {exc}"
        topics_payload = _build_topics_payload_for_error("internal_error", error_summary)
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "internal_error",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": account_info,
            "topics": topics_payload,
        }

    # Recent events for the primary topic in the last 24h
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    recent_q = db.query(EbayEvent).filter(EbayEvent.topic == primary_topic_id)
    recent_q = recent_q.filter(
        or_(
            and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time >= window_start),
            and_(EbayEvent.event_time.is_(None), EbayEvent.created_at >= window_start),
        )
    )
    recent_count = recent_q.count()

    latest = (
        db.query(EbayEvent)
        .filter(EbayEvent.topic == primary_topic_id)
        .order_by(
            EbayEvent.event_time.desc().nullslast(),
            EbayEvent.created_at.desc(),
        )
        .first()
    )
    last_event_time = None
    if latest:
        last_event_time = (latest.event_time or latest.created_at).isoformat() if (
            latest.event_time or latest.created_at
        ) else None

    state = "misconfigured"
    reason: str | None = None
    dest_status: str | None = None
    sub_status: str | None = None
    verification_status: str | None = None

    if dest is None:
        reason = "no_destination"
    else:
        dest_status = (dest.get("status") or "").upper() or "UNKNOWN"
        delivery_cfg = dest.get("deliveryConfig") or {}
        raw_ver_status = delivery_cfg.get("verificationStatus")
        if isinstance(raw_ver_status, str) and raw_ver_status:
            verification_status = raw_ver_status.upper()
        sub_status = (sub.get("status") or "").upper() if sub else None

        if dest_status != "INACTIVE" and dest_status != "ENABLED":
            # Destination exists but is not in an active state.
            reason = "destination_disabled"
        elif verification_status and verification_status not in ("CONFIRMED", "VERIFIED"):
            # eBay may report UNCONFIRMED / PENDING while the challenge flow is in progress.
            reason = "verification_pending"
        elif sub is None:
            reason = "no_subscription"
        elif sub_status not in (None, "ENABLED"):
            reason = "subscription_not_enabled"
        elif recent_count == 0:
            state = "no_events"
            reason = "no_recent_events"
        else:
            state = "ok"
            reason = "subscription_enabled"

    dest_id = dest.get("destinationId") or dest.get("id") if dest else None
    sub_id = sub.get("subscriptionId") or sub.get("id") if sub else None

    # Build per-topic status array for Diagnostics UI.
    topics_payload: list[dict] = []
    for topic_cfg in SUPPORTED_TOPICS:
        topic_id = topic_cfg.topic_id
        topic_error_reason: str | None = None
        topic_error_summary: str | None = None

        # Reuse primary topic data when possible; otherwise best-effort call.
        if topic_id == primary_topic_id:
            t_dest = dest
            t_sub = sub
        else:
            try:
                t_dest, t_sub = await ebay_service.get_notification_status(
                    access_token,
                    endpoint_url,
                    topic_id,
                )
            except HTTPException as exc:
                logger.error(
                    "Notification status check failed for topic %s via Notification API: status=%s detail=%s",
                    topic_id,
                    exc.status_code,
                    exc.detail,
                )
                detail = exc.detail
                if isinstance(detail, dict):
                    nerr = {
                        "status_code": detail.get("status_code", exc.status_code),
                        "message": detail.get("message") or str(detail),
                        "body": detail.get("body"),
                    }
                else:
                    nerr = {"status_code": exc.status_code, "message": str(detail)}

                topic_error_reason = "notification_api_error"
                body_obj = nerr.get("body")
                body_preview = body_obj
                if isinstance(body_preview, (dict, list)):
                    body_preview = str(body_preview)[:300]
                topic_error_summary = f"Notification API HTTP {nerr.get('status_code')} - {nerr.get('message')}"
                if body_preview:
                    topic_error_summary += f" | body: {body_preview}"

                t_dest, t_sub = None, None
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Unexpected error while checking Notification API status for topic %s",
                    topic_id,
                )
                topic_error_reason = "internal_error"
                topic_error_summary = str(exc)
                t_dest, t_sub = None, None

        t_dest_id = t_dest.get("destinationId") or t_dest.get("id") if t_dest else None
        t_sub_id = t_sub.get("subscriptionId") or t_sub.get("id") if t_sub else None

        t_dest_status: str | None = None
        t_sub_status: str | None = None
        t_verification_status: str | None = None
        if t_dest is not None:
            t_dest_status = (t_dest.get("status") or "").upper() or "UNKNOWN"
            t_delivery_cfg = t_dest.get("deliveryConfig") or {}
            t_raw_ver = t_delivery_cfg.get("verificationStatus")
            if isinstance(t_raw_ver, str) and t_raw_ver:
                t_verification_status = t_raw_ver.upper()
            t_sub_status = (t_sub.get("status") or "").upper() if t_sub else None

        # Topic metadata (scope) is best-effort; errors here do not affect core state.
        topic_scope: str | None = None
        try:
            topic_meta = await ebay_service.get_notification_topic_metadata(
                access_token,
                topic_id,
            )
            raw_scope = topic_meta.get("scope")
            if isinstance(raw_scope, str) and raw_scope:
                topic_scope = raw_scope.upper()
        except Exception:
            topic_scope = None

        token_type: str | None = None
        if topic_scope == "APPLICATION":
            token_type = "application"
        elif topic_scope == "USER":
            token_type = "user"

        # Recent events per topic (24h window), independent of primary stats.
        topic_recent_q = db.query(EbayEvent).filter(EbayEvent.topic == topic_id)
        topic_recent_q = topic_recent_q.filter(
            or_(
                and_(
                    EbayEvent.event_time.isnot(None),
                    EbayEvent.event_time >= window_start,
                ),
                and_(
                    EbayEvent.event_time.is_(None),
                    EbayEvent.created_at >= window_start,
                ),
            )
        )
        topic_recent_count = topic_recent_q.count()

        topic_latest = (
            db.query(EbayEvent)
            .filter(EbayEvent.topic == topic_id)
            .order_by(
                EbayEvent.event_time.desc().nullslast(),
                EbayEvent.created_at.desc(),
            )
            .first()
        )
        topic_last_event_time: str | None = None
        if topic_latest:
            base_ts = topic_latest.event_time or topic_latest.created_at
            topic_last_event_time = base_ts.isoformat() if base_ts else None

        topic_status_flag: str | None = None
        if topic_error_reason is not None:
            topic_status_flag = "ERROR"
        elif t_dest_status == "ENABLED" and (
            not t_verification_status or t_verification_status in ("CONFIRMED", "VERIFIED")
        ) and t_sub_status == "ENABLED":
            topic_status_flag = "OK"

        topics_payload.append(
            {
                "topicId": topic_id,
                "scope": topic_scope,
                "destinationId": t_dest_id,
                "subscriptionId": t_sub_id,
                "destinationStatus": t_dest_status,
                "subscriptionStatus": t_sub_status,
                "verificationStatus": t_verification_status,
                "tokenType": token_type,
                "status": topic_status_flag,
                "error": topic_error_summary,
                "recentEvents": {
                    "count": topic_recent_count,
                    "lastEventTime": topic_last_event_time,
                },
            }
        )

        # Derive a concise error summary for non-OK states so the UI does not
        # have to guess based on ``state``/``reason``.
        error_summary: Optional[str] = None
        if state == "no_events":
            error_summary = "No recent events received for the primary webhook topic in the last 24 hours."
        elif state == "misconfigured":
            if reason == "no_destination":
                error_summary = "Notification destination does not exist for the configured webhook URL."
            elif reason == "destination_disabled":
                error_summary = "Notification destination is not ENABLED."
            elif reason == "verification_pending":
                # eBay may report UNCONFIRMED / PENDING while the challenge flow is in progress.
                error_summary = "Notification destination verification is not yet complete."
            elif reason == "no_subscription":
                error_summary = "No subscription exists for the primary webhook topic."
            elif reason == "subscription_not_enabled":
                error_summary = "Subscription for the primary webhook topic is not ENABLED."
    ok = state == "ok"

    return {
        "ok": ok,
        "environment": env,
        "webhookUrl": endpoint_url,
        "state": state,
        "reason": reason,
        "destination": dest,
        "subscription": sub,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "destinationStatus": dest_status,
        "subscriptionStatus": sub_status,
        "verificationStatus": verification_status,
        "recentEvents": {"count": recent_count, "lastEventTime": last_event_time},
        "checkedAt": checked_at,
        "account": account_info,
        "topics": topics_payload,
        "errorSummary": error_summary,
    }


@router.post("/notifications/test-marketplace-deletion")
async def test_marketplace_account_deletion_notification(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Trigger a Notification API test for MARKETPLACE_ACCOUNT_DELETION.

    This endpoint ensures that a destination and subscription exist for the
    configured webhook URL, then calls the Notification API test operation.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL
    logger.info(
        "[notifications:test] Starting MARKETPLACE_ACCOUNT_DELETION test env=%s endpoint_url=%s user_id=%s",
        env,
        endpoint_url,
        current_user.id,
    )

    if not endpoint_url:
        payload = {
            "ok": False,
            "reason": "no_destination_url",
            "message": "EBAY_NOTIFICATION_DESTINATION_URL is not configured on the backend.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        payload = {
            "ok": False,
            "reason": "no_account",
            "message": "No active eBay account found for this organization.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        payload = {
            "ok": False,
            "reason": "no_access_token",
            "message": "No eBay access token available for the selected account.",
            "environment": env,
            "account": {
                "id": str(account.id),
                "username": account.username or account.ebay_user_id,
                "environment": env,
            },
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    access_token = token.access_token
    verification_token = settings.EBAY_NOTIFICATION_VERIFICATION_TOKEN
    if not verification_token:
        payload = {
            "ok": False,
            "reason": "no_verification_token",
            "message": "EBAY_NOTIFICATION_VERIFICATION_TOKEN is required to create a destination.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    topic_id = "MARKETPLACE_ACCOUNT_DELETION"
    debug_log: list[str] = []
    account_info = {
        "id": str(account.id),
        "username": account.username or account.ebay_user_id,
        "environment": env,
    }
    try:
        logger.info(
            "[notifications:test] Ensuring destination for account_id=%s username=%s",
            account.id,
            account.username,
        )
        dest = await ebay_service.ensure_notification_destination(
            access_token,
            endpoint_url,
            verification_token=verification_token,
            debug_log=debug_log,
        )
        dest_id = dest.get("destinationId") or dest.get("id")
        logger.info("[notifications:test] Destination ready id=%s", dest_id)

        # For MARKETPLACE_ACCOUNT_DELETION (APPLICATION-scope topic), use an
        # application access token (client_credentials) for subscription and
        # test calls, per eBay Notification API requirements.
        app_access_token = await ebay_service.get_app_access_token()
        debug_log.append("[token] Using eBay application access token (client_credentials) for subscription + test")

        sub = await ebay_service.ensure_notification_subscription(
            access_token,
            dest_id,
            topic_id,
            debug_log=debug_log,
        )
        sub_id = sub.get("subscriptionId") or sub.get("id")
        logger.info("[notifications:test] Subscription ready id=%s status=%s", sub_id, sub.get("status"))

        if not sub_id:
            msg = (
                "Subscription was created or retrieved but subscriptionId is missing; "
                "cannot invoke Notification API test for MARKETPLACE_ACCOUNT_DELETION."
            )
            logger.error("[notifications:test] %s", msg)
            debug_log.append(f"[subscription] ERROR: {msg}")
            payload = {
                "ok": False,
                "reason": "no_subscription_id",
                "message": msg,
                "environment": env,
                "webhookUrl": endpoint_url,
                "logs": debug_log,
                "account": account_info,
            }
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

        test_result = await ebay_service.test_notification_subscription(
            app_access_token,
            sub_id,
            debug_log=debug_log,
        )
        logger.info(
            "[notifications:test] Test notification call completed status_code=%s",
            test_result.get("status_code"),
        )
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            notification_error = {
                "status_code": detail.get("status_code", exc.status_code),
                "message": detail.get("message") or str(detail),
                "body": detail.get("body"),
            }
        else:
            notification_error = {
                "status_code": exc.status_code,
                "message": str(detail),
            }

        body_preview = notification_error.get("body")
        if isinstance(body_preview, (dict, list)):
            body_preview = str(body_preview)[:300]
        error_summary = f"Notification API HTTP {notification_error.get('status_code')} - {notification_error.get('message')}"
        if body_preview:
            error_summary += f" | body: {body_preview}"

        logger.error(
            "[notifications:test] Notification API error during test: %s",
            notification_error,
        )
        payload = {
            "ok": False,
            "reason": "notification_api_error",
            "message": "Notification API returned an error while creating destination/subscription or sending the test notification.",
            "environment": env,
            "webhookUrl": endpoint_url,
            "notificationError": notification_error,
            "errorSummary": error_summary,
            "logs": debug_log,
            "account": account_info,
            "error": error_summary,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.error("[notifications:test] Unexpected error during notification test", exc_info=True)
        message = f"Unexpected error: {type(exc).__name__}: {exc}"
        payload = {
            "ok": False,
            "reason": "unexpected_error",
            "message": message,
            "environment": env,
            "webhookUrl": endpoint_url,
            "account": account_info,
            "error": message,
        }
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)

    return {
        "ok": True,
        "environment": env,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "message": "Test notification requested; check ebay_events and Notifications UI.",
        "notificationTest": test_result,
        "logs": debug_log,
        "account": account_info,
    }


@router.post("/notifications/test-topic")
async def test_notification_topic(
    body: dict,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Generic Notification API test endpoint for an arbitrary topicId.

    For now this is effectively limited to the topics listed in
    ``SUPPORTED_TOPICS`` (MARKETPLACE_ACCOUNT_DELETION in Phase 1), but the
    wiring is generic so that future order/fulfillment/finances topics can be
    added without changing this handler.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL

    topic_raw = body.get("topicId") or body.get("topic_id")
    topic_id = str(topic_raw).strip() if topic_raw is not None else ""
    supported_topic_ids = {cfg.topic_id for cfg in SUPPORTED_TOPICS}

    if not topic_id:
        payload = {
            "ok": False,
            "reason": "missing_topic_id",
            "message": "Request body must include topicId.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    if topic_id not in supported_topic_ids:
        payload = {
            "ok": False,
            "reason": "unsupported_topic",
            "message": f"TopicId {topic_id!r} is not configured for this application.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    logger.info(
        "[notifications:test] Starting generic notification test topic=%s env=%s endpoint_url=%s user_id=%s",
        topic_id,
        env,
        endpoint_url,
        current_user.id,
    )

    if not endpoint_url:
        payload = {
            "ok": False,
            "reason": "no_destination_url",
            "message": "EBAY_NOTIFICATION_DESTINATION_URL is not configured on the backend.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        payload = {
            "ok": False,
            "reason": "no_account",
            "message": "No active eBay account found for this organization.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        payload = {
            "ok": False,
            "reason": "no_access_token",
            "message": "No eBay access token available for the selected account.",
            "environment": env,
            "account": {
                "id": str(account.id),
                "username": account.username or account.ebay_user_id,
                "environment": env,
            },
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    access_token = token.access_token
    verification_token = settings.EBAY_NOTIFICATION_VERIFICATION_TOKEN
    if not verification_token:
        payload = {
            "ok": False,
            "reason": "no_verification_token",
            "message": "EBAY_NOTIFICATION_VERIFICATION_TOKEN is required to create a destination.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    debug_log: list[str] = []
    account_info = {
        "id": str(account.id),
        "username": account.username or account.ebay_user_id,
        "environment": env,
    }

    try:
        logger.info(
            "[notifications:test] Ensuring destination for account_id=%s username=%s topic=%s",
            account.id,
            account.username,
            topic_id,
        )
        dest = await ebay_service.ensure_notification_destination(
            access_token,
            endpoint_url,
            verification_token=verification_token,
            debug_log=debug_log,
        )
        dest_id = dest.get("destinationId") or dest.get("id")
        logger.info("[notifications:test] Destination ready id=%s", dest_id)

        sub = await ebay_service.ensure_notification_subscription(
            access_token,
            dest_id,
            topic_id,
            debug_log=debug_log,
        )
        sub_id = sub.get("subscriptionId") or sub.get("id")
        logger.info(
            "[notifications:test] Subscription ready id=%s status=%s topic=%s",
            sub_id,
            sub.get("status"),
            topic_id,
        )

        if not sub_id:
            msg = (
                "Subscription was created or retrieved but subscriptionId is missing; "
                f"cannot invoke Notification API test for topic {topic_id}."
            )
            logger.error("[notifications:test] %s", msg)
            debug_log.append(f"[subscription] ERROR: {msg}")
            payload = {
                "ok": False,
                "reason": "no_subscription_id",
                "message": msg,
                "environment": env,
                "webhookUrl": endpoint_url,
                "logs": debug_log,
                "account": account_info,
                "topicId": topic_id,
            }
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

        # Decide which token type to use for the test call based on topic scope.
        topic_meta = await ebay_service.get_notification_topic_metadata(
            access_token,
            topic_id,
            debug_log=debug_log,
        )
        raw_scope = topic_meta.get("scope") if isinstance(topic_meta, dict) else None
        scope_upper = raw_scope.upper() if isinstance(raw_scope, str) else None

        if scope_upper == "APPLICATION":
            app_access_token = await ebay_service.get_app_access_token()
            test_access_token = app_access_token
            debug_log.append(
                "[token] Using eBay application access token (client_credentials) for subscription + test",
            )
            token_type = "application"
        else:
            test_access_token = access_token
            debug_log.append("[token] Using eBay user access token for subscription + test")
            token_type = "user"

        test_result = await ebay_service.test_notification_subscription(
            test_access_token,
            sub_id,
            debug_log=debug_log,
        )
        logger.info(
            "[notifications:test] Test notification call completed status_code=%s topic=%s",
            test_result.get("status_code"),
            topic_id,
        )

        # Optional: process recently received events so that [event] lines can
        # be surfaced in the debug log for this test. This is best-effort and
        # will be a no-op until the ingestion helper is implemented.
        try:
            from ..services.ebay_event_processor import process_pending_events  # type: ignore[attr-defined]

            summary = process_pending_events(limit=50, debug_log=debug_log)
            logger.info(
                "[notifications:test] Processed pending events after test topic=%s summary=%s",
                topic_id,
                summary,
            )
        except Exception:
            # Ingestion failures must not break the Notification API test flow.
            logger.warning(
                "[notifications:test] Failed to process pending events after test for topic=%s",
                topic_id,
                exc_info=True,
            )

    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            notification_error = {
                "status_code": detail.get("status_code", exc.status_code),
                "message": detail.get("message") or str(detail),
                "body": detail.get("body"),
            }
        else:
            notification_error = {
                "status_code": exc.status_code,
                "message": str(detail),
            }

        body_preview = notification_error.get("body")
        if isinstance(body_preview, (dict, list)):
            body_preview = str(body_preview)[:300]
        error_summary = f"Notification API HTTP {notification_error.get('status_code')} - {notification_error.get('message')}"
        if body_preview:
            error_summary += f" | body: {body_preview}"

        logger.error(
            "[notifications:test] Notification API error during generic test topic=%s error=%s",
            topic_id,
            notification_error,
        )
        payload = {
            "ok": False,
            "reason": "notification_api_error",
            "message": "Notification API returned an error while creating destination/subscription or sending the test notification.",
            "environment": env,
            "webhookUrl": endpoint_url,
            "notificationError": notification_error,
            "errorSummary": error_summary,
            "logs": debug_log,
            "account": account_info,
            "topicId": topic_id,
            "error": error_summary,
            "tokenType": token_type if 'token_type' in locals() else None,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.error(
            "[notifications:test] Unexpected error during generic notification test topic=%s",
            topic_id,
            exc_info=True,
        )
        message = f"Unexpected error: {type(exc).__name__}: {exc}"
        payload = {
            "ok": False,
            "reason": "unexpected_error",
            "message": message,
            "environment": env,
            "webhookUrl": endpoint_url,
            "account": account_info,
            "topicId": topic_id,
            "error": message,
        }
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)

    return {
        "ok": True,
        "environment": env,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "message": "Test notification requested; check ebay_events and Notifications UI.",
        "notificationTest": test_result,
        "logs": debug_log,
        "account": account_info,
        "topicId": topic_id,
        "tokenType": token_type,
    }
