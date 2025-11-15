from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models_sqlalchemy.ebay_workers import (
    EbaySyncState,
    EbayWorkerGlobalConfig,
)


API_FAMILIES = [
    "orders",
    "finances",
    "messages",
    "seller_transactions",
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_global_config(db: Session) -> EbayWorkerGlobalConfig:
    cfg = db.query(EbayWorkerGlobalConfig).first()
    if cfg:
        return cfg
    cfg = EbayWorkerGlobalConfig(
        id=str(uuid4()),
        workers_enabled=True,
        defaults_json={
            "overlap_minutes": 60,
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
