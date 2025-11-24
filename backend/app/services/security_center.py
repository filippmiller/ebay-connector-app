from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models_sqlalchemy.models import SecuritySettings, SecurityEvent, LoginAttempt, User
from app.utils.logger import logger


UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(UTC)


def get_or_create_security_settings(db: Session) -> SecuritySettings:
    """Load the singleton SecuritySettings row or create it with defaults.

    This helper is safe to call on every login/admin request; it keeps logic
    for seeding defaults in one place.
    """

    settings: Optional[SecuritySettings] = (
        db.query(SecuritySettings).order_by(SecuritySettings.id.asc()).first()
    )
    if settings:
        return settings

    settings = SecuritySettings()  # relies on model-level defaults
    db.add(settings)
    try:
        db.commit()
    except Exception:
        logger.exception("Failed to create initial SecuritySettings row; rolling back")
        db.rollback()
        # Best-effort: try to read again in case another worker created it.
        settings = (
            db.query(SecuritySettings).order_by(SecuritySettings.id.asc()).first()
        )
        if settings:
            return settings
        raise

    db.refresh(settings)
    logger.info("SecuritySettings row created with default values (id=%s)", settings.id)
    return settings


def get_effective_session_ttl_minutes(settings: Optional[SecuritySettings], fallback_minutes: int) -> int:
    """Return the session TTL in minutes based on SecuritySettings.

    If settings is None or misconfigured, fall back to the provided value.
    """

    if not settings:
        return fallback_minutes
    try:
        ttl = int(settings.session_ttl_minutes)
        if ttl <= 0:
            return fallback_minutes
        return ttl
    except Exception:
        return fallback_minutes


def check_pre_login_block(
    db: Session,
    *,
    email: str,
    ip_address: Optional[str],
    now: Optional[datetime] = None,
) -> Tuple[bool, Optional[datetime]]:
    """Check whether the given email+IP combination is currently blocked.

    Returns (is_blocked, block_until).
    """

    if not now:
        now = _utcnow()

    q = db.query(LoginAttempt).filter(LoginAttempt.block_applied.is_(True))
    q = q.filter(LoginAttempt.email == email)
    if ip_address:
        q = q.filter(LoginAttempt.ip_address == ip_address)
    latest_block = q.order_by(LoginAttempt.block_until.desc().nullslast()).first()

    if latest_block and latest_block.block_until and latest_block.block_until > now:
        return True, latest_block.block_until

    return False, None


def _create_security_event(
    db: Session,
    *,
    event_type: str,
    user: Optional[User] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> SecurityEvent:
    if not now:
        now = _utcnow()

    ev = SecurityEvent(
        user_id=str(user.id) if user is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
        event_type=event_type,
        description=description,
        created_at=now,
        metadata=metadata or {},
    )
    db.add(ev)
    return ev


def _compute_series_and_streak(
    attempts: list[LoginAttempt],
    *,
    max_failed_attempts: int,
) -> tuple[int, int]:
    """Compute completed failure series and current failure streak.

    A "series" is defined as max_failed_attempts consecutive failed attempts
    without an intervening success. Blocked attempts (block_applied=True) do
    not count toward the streak to avoid compounding penalties while already
    blocked.
    """

    series_count = 0
    current_streak = 0

    for att in sorted(attempts, key=lambda a: a.created_at or datetime.min):
        if att.success:
            current_streak = 0
            continue
        if att.block_applied:
            # Attempts that were rejected due to an existing block should not
            # advance the progression further.
            continue
        # Treat any non-success, non-blocked attempt as a failure for streak
        current_streak += 1
        if current_streak >= max_failed_attempts:
            series_count += 1
            current_streak = 0

    return series_count, current_streak


def record_login_attempt_and_events(
    db: Session,
    *,
    email: str,
    user: Optional[User],
    ip_address: Optional[str],
    user_agent: Optional[str],
    success: bool,
    reason: Optional[str],
    settings: SecuritySettings,
    now: Optional[datetime] = None,
    preblocked: bool = False,
) -> tuple[LoginAttempt, Optional[SecurityEvent], Optional[SecurityEvent]]:
    """Insert a LoginAttempt row and corresponding SecurityEvent(s).

    Returns (login_attempt, primary_event, optional_block_event).

    - When success=True, no new block is applied and event_type is
      "login_success".
    - When success=False and preblocked=True, event_type is "login_blocked"
      and no additional series-based block is computed.
    - When success=False and not preblocked, this helper computes whether the
      new failure completes a series of failures and, if so, schedules a new
      block window via block_until and logs a "login_blocked" event.
    """

    if not now:
        now = _utcnow()

    primary_event: Optional[SecurityEvent] = None
    block_event: Optional[SecurityEvent] = None

    # Default: no new block window
    block_applied = False
    block_until: Optional[datetime] = None

    if success:
        primary_event = _create_security_event(
            db,
            event_type="login_success",
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            description="User login succeeded",
            metadata={"email": email},
            now=now,
        )
    else:
        # Failed login; distinguish between preblocked vs credential failure.
        event_type = "login_blocked" if preblocked else "login_failed"
        desc = (
            "Login attempt rejected due to active block window"
            if preblocked
            else "User login failed"
        )
        primary_event = _create_security_event(
            db,
            event_type=event_type,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            description=desc,
            metadata={"email": email, "reason": reason or event_type},
            now=now,
        )

        if not preblocked:
            # Compute whether this new failure should start a new block window.
            max_failed = settings.max_failed_attempts or 3
            # Fetch a bounded history for this identity+IP to keep the query cheap.
            history_q = db.query(LoginAttempt).filter(LoginAttempt.email == email)
            if ip_address:
                history_q = history_q.filter(LoginAttempt.ip_address == ip_address)
            # Only consider attempts up to "now" (exclude the row we are about to insert).
            history_q = history_q.filter(
                LoginAttempt.created_at <= now,
            ).order_by(LoginAttempt.created_at.desc()).limit(200)

            history = list(history_q.all())
            series_count, current_streak = _compute_series_and_streak(
                history,
                max_failed_attempts=max_failed,
            )

            # Incorporate this new failure into the streak.
            new_streak = current_streak + 1
            if new_streak >= max_failed:
                # This failure completes another series.
                series_index = series_count + 1
                initial = settings.initial_block_minutes or 1
                step = settings.progressive_delay_step_minutes or 2
                max_delay = settings.max_delay_minutes or 30

                block_minutes = initial + (series_index - 1) * step
                if block_minutes > max_delay:
                    block_minutes = max_delay

                block_applied = True
                block_until = now + timedelta(minutes=block_minutes)

                block_event = _create_security_event(
                    db,
                    event_type="login_blocked",
                    user=user,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    description=(
                        "Too many failed login attempts; identity temporarily blocked"
                    ),
                    metadata={
                        "email": email,
                        "series_index": series_index,
                        "max_failed_attempts": max_failed,
                        "block_minutes": block_minutes,
                        "block_until": block_until.isoformat(),
                    },
                    now=now,
                )

    attempt = LoginAttempt(
        created_at=now,
        email=email,
        user_id=str(user.id) if user is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
        success=bool(success),
        reason=reason,
        block_applied=block_applied,
        block_until=block_until,
        metadata={},
    )
    db.add(attempt)

    # Flush so that attempt.id and event ids are populated if needed by callers.
    db.flush()

    return attempt, primary_event, block_event
