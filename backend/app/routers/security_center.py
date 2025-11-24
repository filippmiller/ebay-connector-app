from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import SecuritySettings, SecurityEvent
from app.services.auth import admin_required
from app.models.user import User
from app.services.security_center import get_or_create_security_settings
from app.utils.logger import logger


router = APIRouter(prefix="/api/admin/security", tags=["admin-security"])

UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(UTC)


# -----------------------------
# Settings endpoints
# -----------------------------


@router.get("/settings")
async def get_security_settings(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the current SecuritySettings row with safe defaults.

    The response is a plain dict so the frontend does not need to know about
    SQLAlchemy models.
    """

    settings = get_or_create_security_settings(db)
    return {
        "id": settings.id,
        "max_failed_attempts": settings.max_failed_attempts,
        "initial_block_minutes": settings.initial_block_minutes,
        "progressive_delay_step_minutes": settings.progressive_delay_step_minutes,
        "max_delay_minutes": settings.max_delay_minutes,
        "enable_captcha": settings.enable_captcha,
        "captcha_after_failures": settings.captcha_after_failures,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "session_idle_timeout_minutes": settings.session_idle_timeout_minutes,
        "bruteforce_alert_threshold_per_ip": settings.bruteforce_alert_threshold_per_ip,
        "bruteforce_alert_threshold_per_user": settings.bruteforce_alert_threshold_per_user,
        "alert_email_enabled": settings.alert_email_enabled,
        "alert_channel": settings.alert_channel,
        "created_at": settings.created_at.isoformat() if settings.created_at else None,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


@router.put("/settings")
async def update_security_settings(
    payload: dict[str, Any],
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update security settings and log a settings_changed event.

    The payload is a simple dict; only known fields are applied. Unknown keys
    are ignored to make the endpoint forwards-compatible.
    """

    settings = get_or_create_security_settings(db)

    # Keep a shallow snapshot for audit logging.
    before = {
        "max_failed_attempts": settings.max_failed_attempts,
        "initial_block_minutes": settings.initial_block_minutes,
        "progressive_delay_step_minutes": settings.progressive_delay_step_minutes,
        "max_delay_minutes": settings.max_delay_minutes,
        "enable_captcha": settings.enable_captcha,
        "captcha_after_failures": settings.captcha_after_failures,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "session_idle_timeout_minutes": settings.session_idle_timeout_minutes,
        "bruteforce_alert_threshold_per_ip": settings.bruteforce_alert_threshold_per_ip,
        "bruteforce_alert_threshold_per_user": settings.bruteforce_alert_threshold_per_user,
        "alert_email_enabled": settings.alert_email_enabled,
        "alert_channel": settings.alert_channel,
    }

    # Apply updates with basic type/limit checks.
    int_fields = [
        "max_failed_attempts",
        "initial_block_minutes",
        "progressive_delay_step_minutes",
        "max_delay_minutes",
        "captcha_after_failures",
        "session_ttl_minutes",
        "session_idle_timeout_minutes",
        "bruteforce_alert_threshold_per_ip",
        "bruteforce_alert_threshold_per_user",
    ]
    bool_fields = [
        "enable_captcha",
        "alert_email_enabled",
    ]
    str_fields = [
        "alert_channel",
    ]

    for field in int_fields:
        if field in payload and payload[field] is not None:
            try:
                value = int(payload[field])
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid integer for field {field}",
                )
            if value < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Field {field} must be non-negative",
                )
            setattr(settings, field, value)

    for field in bool_fields:
        if field in payload and payload[field] is not None:
            setattr(settings, field, bool(payload[field]))

    for field in str_fields:
        if field in payload:
            raw = payload[field]
            if raw is None:
                setattr(settings, field, None)
            else:
                setattr(settings, field, str(raw))

    # Persist changes and log a settings_changed event.
    now = _utcnow()
    settings.updated_at = now

    # Compute a small diff for the event metadata.
    after = {
        "max_failed_attempts": settings.max_failed_attempts,
        "initial_block_minutes": settings.initial_block_minutes,
        "progressive_delay_step_minutes": settings.progressive_delay_step_minutes,
        "max_delay_minutes": settings.max_delay_minutes,
        "enable_captcha": settings.enable_captcha,
        "captcha_after_failures": settings.captcha_after_failures,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "session_idle_timeout_minutes": settings.session_idle_timeout_minutes,
        "bruteforce_alert_threshold_per_ip": settings.bruteforce_alert_threshold_per_ip,
        "bruteforce_alert_threshold_per_user": settings.bruteforce_alert_threshold_per_user,
        "alert_email_enabled": settings.alert_email_enabled,
        "alert_channel": settings.alert_channel,
    }

    changes: dict[str, Any] = {}
    for key, before_val in before.items():
        after_val = after.get(key)
        if before_val != after_val:
            changes[key] = {"before": before_val, "after": after_val}

    if changes:
        ev = SecurityEvent(
            user_id=str(current_user.id),
            ip_address=None,
            user_agent=None,
            event_type="settings_changed",
            description="Security settings updated via admin UI",
            metadata={"changes": changes},
            created_at=now,
        )
        db.add(ev)

    db.commit()
    db.refresh(settings)

    logger.info("Security settings updated by user_id=%s changes=%s", current_user.id, list(changes.keys()))

    return {
        "ok": True,
        "settings": {
            "id": settings.id,
            "max_failed_attempts": settings.max_failed_attempts,
            "initial_block_minutes": settings.initial_block_minutes,
            "progressive_delay_step_minutes": settings.progressive_delay_step_minutes,
            "max_delay_minutes": settings.max_delay_minutes,
            "enable_captcha": settings.enable_captcha,
            "captcha_after_failures": settings.captcha_after_failures,
            "session_ttl_minutes": settings.session_ttl_minutes,
            "session_idle_timeout_minutes": settings.session_idle_timeout_minutes,
            "bruteforce_alert_threshold_per_ip": settings.bruteforce_alert_threshold_per_ip,
            "bruteforce_alert_threshold_per_user": settings.bruteforce_alert_threshold_per_user,
            "alert_email_enabled": settings.alert_email_enabled,
            "alert_channel": settings.alert_channel,
            "created_at": settings.created_at.isoformat() if settings.created_at else None,
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
        },
    }


# -----------------------------
# Events listing + export
# -----------------------------


@router.get("/events")
async def list_security_events(
    event_type: Optional[str] = Query(None, description="Filter by event_type"),
    user_id: Optional[str] = Query(None, description="Filter by user id"),
    ip: Optional[str] = Query(None, alias="ip", description="Filter by IP address"),
    from_ts: Optional[str] = Query(None, alias="from", description="ISO timestamp lower bound"),
    to_ts: Optional[str] = Query(None, alias="to", description="ISO timestamp upper bound"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List security events for the Security Center Events/Logs tab."""

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

    query = db.query(SecurityEvent)

    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    if user_id:
        query = query.filter(SecurityEvent.user_id == user_id)
    if ip:
        query = query.filter(SecurityEvent.ip_address == ip)

    from_dt = _parse_iso(from_ts)
    to_dt = _parse_iso(to_ts)

    if from_dt:
        query = query.filter(SecurityEvent.created_at >= from_dt)
    if to_dt:
        query = query.filter(SecurityEvent.created_at <= to_dt)

    total = query.count()

    query = query.order_by(desc(SecurityEvent.created_at))
    events = query.offset(offset).limit(limit).all()

    items = []
    for ev in events:
        items.append(
            {
                "id": ev.id,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
                "user_id": ev.user_id,
                "ip_address": ev.ip_address,
                "user_agent": ev.user_agent,
                "event_type": ev.event_type,
                "description": ev.description,
                "metadata": ev.metadata or {},
            }
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/events/export")
async def export_security_events(
    event_type: Optional[str] = Query(None, description="Filter by event_type"),
    user_id: Optional[str] = Query(None, description="Filter by user id"),
    ip: Optional[str] = Query(None, alias="ip", description="Filter by IP address"),
    from_ts: Optional[str] = Query(None, alias="from", description="ISO timestamp lower bound"),
    to_ts: Optional[str] = Query(None, alias="to", description="ISO timestamp upper bound"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Export security events as JSON for now (CSV can be added later).

    This endpoint intentionally mirrors the filters of /events but returns all
    matching rows without pagination, so the frontend can trigger a file
    download.
    """

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

    query = db.query(SecurityEvent)

    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    if user_id:
        query = query.filter(SecurityEvent.user_id == user_id)
    if ip:
        query = query.filter(SecurityEvent.ip_address == ip)

    from_dt = _parse_iso(from_ts)
    to_dt = _parse_iso(to_ts)

    if from_dt:
        query = query.filter(SecurityEvent.created_at >= from_dt)
    if to_dt:
        query = query.filter(SecurityEvent.created_at <= to_dt)

    query = query.order_by(desc(SecurityEvent.created_at))
    events = query.all()

    rows = []
    for ev in events:
        rows.append(
            {
                "id": ev.id,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
                "user_id": ev.user_id,
                "ip_address": ev.ip_address,
                "user_agent": ev.user_agent,
                "event_type": ev.event_type,
                "description": ev.description,
                "metadata": ev.metadata or {},
            }
        )

    return {"rows": rows}


# -----------------------------
# Overview metrics
# -----------------------------


@router.get("/overview")
async def security_overview(
    window_hours: int = Query(24, ge=1, le=7 * 24, description="Lookback window in hours"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return high-level security metrics for the Overview tab."""

    now = _utcnow()
    window_start = now - timedelta(hours=window_hours)

    base_q = db.query(SecurityEvent).filter(SecurityEvent.created_at >= window_start)

    def _count(event_type: str) -> int:
        return base_q.filter(SecurityEvent.event_type == event_type).count()

    metrics = {
        "login_success": _count("login_success"),
        "login_failed": _count("login_failed"),
        "login_blocked": _count("login_blocked"),
        "settings_changed": _count("settings_changed"),
        "security_alert": _count("security_alert"),
    }

    # Top IPs by failed attempts in the window.
    from sqlalchemy import func

    top_failed_ips = (
        db.query(SecurityEvent.ip_address, func.count(SecurityEvent.id).label("cnt"))
        .filter(
            SecurityEvent.created_at >= window_start,
            SecurityEvent.event_type.in_(["login_failed", "login_blocked"]),
            SecurityEvent.ip_address.isnot(None),
        )
        .group_by(SecurityEvent.ip_address)
        .order_by(desc("cnt"))
        .limit(10)
        .all()
    )

    top_ips = [
        {"ip_address": ip, "count": int(cnt)} for ip, cnt in top_failed_ips if ip is not None
    ]

    return {
        "window_hours": window_hours,
        "from": window_start.isoformat(),
        "to": now.isoformat(),
        "metrics": metrics,
        "top_failed_ips": top_ips,
    }
