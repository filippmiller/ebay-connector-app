from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from typing import Optional, Any
import os
from datetime import datetime, timezone, timedelta

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import SyncLog, EbayAccount, EbayToken, EbayAuthorization, EbayScopeDefinition, EbayEvent
from ..services.auth import admin_required
from ..models.user import User
from ..utils.logger import logger
from ..services.ebay import ebay_service
from ..services.ebay_connect_logger import ebay_connect_logger
from ..config import settings

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


@router.get("/notifications/status")
async def get_notifications_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return high-level health for the Notifications Center webhook.

    Status is derived from Notification API destination/subscription state and
    the presence of recent MARKETPLACE_ACCOUNT_DELETION events.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL

    if not endpoint_url:
        return {
            "environment": env,
            "webhookUrl": None,
            "state": "misconfigured",
            "reason": "missing_destination_url",
            "destination": None,
            "subscription": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
        }

    # Pick first active account for this org
    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        return {
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "no_account",
            "destination": None,
            "subscription": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
        }

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        return {
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "no_access_token",
            "destination": None,
            "subscription": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
        }

    access_token = token.access_token

    # Query Notification API for destination + subscription state
    topic_id = "MARKETPLACE_ACCOUNT_DELETION"
    try:
        dest, sub = await ebay_service.get_notification_status(access_token, endpoint_url, topic_id)
    except HTTPException as exc:
        # Surface Notification API error as misconfigured state
        return {
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "notification_api_error",
            "notificationError": exc.detail,
            "destination": None,
            "subscription": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
        }

    # Recent events for this topic in the last 24h
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    recent_q = db.query(EbayEvent).filter(EbayEvent.topic == topic_id)
    recent_q = recent_q.filter(
        or_(
            and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time >= window_start),
            and_(EbayEvent.event_time.is_(None), EbayEvent.created_at >= window_start),
        )
    )
    recent_count = recent_q.count()

    latest = (
        db.query(EbayEvent)
        .filter(EbayEvent.topic == topic_id)
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
    reason = None
    if dest is None:
        reason = "no_destination"
    else:
        dest_status = (dest.get("status") or "").upper() or "UNKNOWN"
        sub_status = (sub.get("status") or "").upper() if sub else None
        if sub is None:
            reason = "no_subscription"
        elif sub_status != "ENABLED":
            reason = "subscription_not_enabled"
        elif recent_count == 0:
            state = "no_events"
            reason = "no_recent_events"
        else:
            state = "ok"
            reason = None

    return {
        "environment": env,
        "webhookUrl": endpoint_url,
        "state": state,
        "reason": reason,
        "destination": dest,
        "subscription": sub,
        "recentEvents": {"count": recent_count, "lastEventTime": last_event_time},
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
    if not endpoint_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EBAY_NOTIFICATION_DESTINATION_URL is not configured",
        )

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_account")

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_access_token")

    access_token = token.access_token
    verification_token = settings.EBAY_NOTIFICATION_VERIFICATION_TOKEN

    # Ensure destination + subscription exist
    topic_id = "MARKETPLACE_ACCOUNT_DELETION"
    dest = await ebay_service.ensure_notification_destination(
        access_token,
        endpoint_url,
        verification_token=verification_token,
    )
    dest_id = dest.get("destinationId") or dest.get("id")

    sub = await ebay_service.ensure_notification_subscription(access_token, dest_id, topic_id)
    sub_id = sub.get("subscriptionId") or sub.get("id")

    test_result = await ebay_service.test_notification_subscription(access_token, sub_id)

    return {
        "ok": True,
        "environment": env,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "message": "Test notification requested; check ebay_events and Notifications UI.",
        "notificationTest": test_result,
    }
