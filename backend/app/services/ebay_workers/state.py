from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models_sqlalchemy.ebay_workers import (
    EbaySyncState,
    EbayWorkerGlobalConfig,
)


API_FAMILIES = [
    "orders",
    "transactions",
    "disputes",
    "offers",
    "messages",
    "active_inventory",
    "cases",
    "finances",
    # Buyer/purchases sync (legacy tbl_ebay_buyer equivalent)
    "buyer",
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def compute_sync_window(
    state: EbaySyncState,
    *,
    now: Optional[datetime] = None,
    overlap_minutes: int = 60,
    initial_backfill_days: int = 90,
) -> Tuple[datetime, datetime]:
    """Compute an incremental sync window for a worker based on its cursor.

    Current policy (for all eBay workers):
    - If ``cursor_value`` exists and parses, start from (cursor - overlap).
    - If ``cursor_value`` is missing or invalid, treat the cursor as ``now``
      and start from (now - overlap).
    - Returns (window_from, window_to) as timezone-aware datetimes.

    ``initial_backfill_days`` is kept for future experimentation but is not
    used by the current eBay workers, which all rely on an overlap-only
    incremental model.
    """

    if now is None:
        now = _now_utc()

    window_to = now

    cursor_raw = state.cursor_value
    if cursor_raw:
        try:
            # Support both "...Z" and "+00:00" styles
            if cursor_raw.endswith("Z"):
                cursor_raw = cursor_raw.replace("Z", "+00:00")
            cursor_dt = datetime.fromisoformat(cursor_raw)
        except Exception:
            # Invalid cursor – fall back to treating it as "now" and only look
            # back by the configured overlap.
            cursor_dt = now
    else:
        # No cursor yet – behave as if the last successful run ended "now" and
        # re-check only the overlap window.
        cursor_dt = now

    window_from = cursor_dt - timedelta(minutes=overlap_minutes)

    return window_from, window_to


def get_or_create_global_config(db: Session) -> EbayWorkerGlobalConfig:
    cfg = db.query(EbayWorkerGlobalConfig).first()
    if cfg:
        return cfg
    cfg = EbayWorkerGlobalConfig(
        id=str(uuid4()),
        workers_enabled=True,
        defaults_json={
            # Global default: 30-minute overlap and 90-day initial backfill.
            "overlap_minutes": 30,
            "initial_backfill_days": 90,
        },
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def are_workers_globally_enabled(db: Session) -> bool:
    cfg = get_or_create_global_config(db)
    return bool(cfg.workers_enabled)


def set_workers_globally_enabled(db: Session, enabled: bool) -> EbayWorkerGlobalConfig:
    cfg = get_or_create_global_config(db)
    cfg.workers_enabled = enabled
    cfg.updated_at = _now_utc()
    db.commit()
    db.refresh(cfg)
    return cfg


def get_or_create_sync_state(
    db: Session,
    *,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
) -> EbaySyncState:
    state = (
        db.query(EbaySyncState)
        .filter(
            EbaySyncState.ebay_account_id == ebay_account_id,
            EbaySyncState.api_family == api_family,
        )
        .first()
    )
    if state:
        return state

    state = EbaySyncState(
        id=str(uuid4()),
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        enabled=True,
        backfill_completed=False,
        cursor_type=None,
        cursor_value=None,
        last_run_at=None,
        last_error=None,
        meta=None,
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def mark_sync_run_result(
    db: Session,
    state: EbaySyncState,
    *,
    cursor_value: Optional[str],
    error: Optional[str] = None,
) -> None:
    """Update sync state after a worker run.

    - If error is None: advance cursor and clear last_error.
    - If error is not None: record last_error but keep cursor as-is.
    """

    state.last_run_at = _now_utc()
    if error:
        state.last_error = error
    else:
        state.last_error = None
        if cursor_value is not None:
            state.cursor_value = cursor_value
    state.updated_at = _now_utc()
    db.commit()


def set_sync_enabled(db: Session, state: EbaySyncState, enabled: bool) -> EbaySyncState:
    state.enabled = enabled
    state.updated_at = _now_utc()
    db.commit()
    db.refresh(state)
    return state
