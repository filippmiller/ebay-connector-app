from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models_sqlalchemy.ebay_workers import EbayWorkerRun, EbaySyncState
from app.utils.logger import logger


RUN_STALE_MINUTES = 10  # after this, running run without heartbeat is considered stale


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_active_run(
    db: Session,
    *,
    ebay_account_id: str,
    api_family: str,
) -> Optional[EbayWorkerRun]:
    """Return a currently active run if it is fresh.

    A run is considered active if status='running' and heartbeat_at is not older
    than RUN_STALE_MINUTES.
    """

    cutoff = _now_utc() - timedelta(minutes=RUN_STALE_MINUTES)
    run = (
        db.query(EbayWorkerRun)
        .filter(
            EbayWorkerRun.ebay_account_id == ebay_account_id,
            EbayWorkerRun.api_family == api_family,
            EbayWorkerRun.status == "running",
        )
        .order_by(EbayWorkerRun.started_at.desc())
        .first()
    )
    if run and run.heartbeat_at and run.heartbeat_at >= cutoff:
        return run
    return None


def start_run(
    db: Session,
    *,
    ebay_account_id: str,
    ebay_user_id: str,
    api_family: str,
) -> Optional[EbayWorkerRun]:
    """Start a new worker run if there is no fresh active run.

    Uses row-level locking on EbaySyncState to prevent race conditions.
    Returns the new run, or None if a fresh run is already in progress.
    """
    
    # Acquire lock on the state row to serialize access to this worker's run state.
    # This prevents two concurrent workers (e.g. web app vs worker service) from
    # both seeing "no active run" and starting one.
    _ = (
        db.query(EbaySyncState)
        .filter(
            EbaySyncState.ebay_account_id == ebay_account_id,
            EbaySyncState.api_family == api_family,
        )
        .with_for_update()
        .first()
    )

    active = get_active_run(db, ebay_account_id=ebay_account_id, api_family=api_family)
    if active:
        logger.info(
            f"Worker run already active for account={ebay_account_id} api={api_family} run_id={active.id}"
        )
        return None

    run = EbayWorkerRun(
        id=str(uuid4()),
        ebay_account_id=ebay_account_id,
        ebay_user_id=ebay_user_id,
        api_family=api_family,
        status="running",
        started_at=_now_utc(),
        heartbeat_at=_now_utc(),
        summary_json=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        f"Started worker run id={run.id} account={ebay_account_id} api={api_family}"
    )
    return run


def heartbeat(db: Session, run: EbayWorkerRun) -> None:
    run.heartbeat_at = _now_utc()
    db.commit()


def complete_run(
    db: Session,
    run: EbayWorkerRun,
    *,
    summary: Optional[dict] = None,
) -> None:
    run.status = "completed"
    run.finished_at = _now_utc()
    run.heartbeat_at = run.finished_at
    if summary is not None:
        run.summary_json = summary
    db.commit()
    logger.info(f"Completed worker run id={run.id} status=completed")


def fail_run(
    db: Session,
    run: EbayWorkerRun,
    *,
    error_message: str,
    summary: Optional[dict] = None,
) -> None:
    run.status = "error"
    run.finished_at = _now_utc()
    run.heartbeat_at = run.finished_at
    if summary is not None:
        run.summary_json = summary
    db.commit()
    logger.error(f"Worker run id={run.id} failed: {error_message}")
