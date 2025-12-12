from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models_sqlalchemy.ebay_workers import EbayApiWorkerLog


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def log_event(
    db: Session,
    *,
    run_id: str,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> EbayApiWorkerLog:
    entry = EbayApiWorkerLog(
        id=str(uuid4()),
        run_id=run_id,
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        event_type=event_type,
        timestamp=_now_utc(),
        details_json=details or {},
    )
    db.add(entry)
    db.commit()
    return entry


def log_start(
    db: Session,
    *,
    run_id: str,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
    window_from: Optional[str],
    window_to: Optional[str],
    limit: Optional[int],
) -> None:
    log_event(
        db,
        run_id=run_id,
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        event_type="start",
        details={
            "window_from": window_from,
            "window_to": window_to,
            "limit": limit,
        },
    )


def log_page(
    db: Session,
    *,
    run_id: str,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
    page: int,
    fetched: int,
    stored: int,
    offset: Optional[int] = None,
) -> None:
    log_event(
        db,
        run_id=run_id,
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        event_type="page",
        details={
            "page": page,
            "fetched": fetched,
            "stored": stored,
            "offset": offset,
        },
    )


def log_done(
    db: Session,
    *,
    run_id: str,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
    total_fetched: int,
    total_stored: int,
    duration_ms: int,
) -> None:
    log_event(
        db,
        run_id=run_id,
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        event_type="done",
        details={
            "total_fetched": total_fetched,
            "total_stored": total_stored,
            "duration_ms": duration_ms,
        },
    )


def log_error(
    db: Session,
    *,
    run_id: str,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
    message: str,
    stage: Optional[str] = None,
) -> None:
    log_event(
        db,
        run_id=run_id,
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        event_type="error",
        details={
            "message": message,
            "stage": stage,
        },
    )
