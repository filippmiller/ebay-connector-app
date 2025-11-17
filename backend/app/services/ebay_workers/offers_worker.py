from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.models_sqlalchemy import SessionLocal
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay import EbayService
from app.utils.logger import logger

from .state import get_or_create_sync_state, mark_sync_run_result
from .runs import start_run, complete_run, fail_run
from .logger import log_start, log_page, log_done, log_error


OFFERS_LIMIT = 200
OVERLAP_MINUTES_DEFAULT = 360
INITIAL_BACKFILL_DAYS_DEFAULT = 90


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_offers_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Offers sync worker for a specific eBay account.

    Mirrors the patterns used by Orders/Transactions workers:
    - per-account + per-API locking via EbayWorkerRun
    - time-based cursor with overlap (default 360 minutes)
    - logs to EbayApiWorkerLog so the terminal can display progress

    Returns the worker run_id if started, or None if skipped.
    """

    db: Session = SessionLocal()
    try:
        account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.warning(f"Offers worker: account {ebay_account_id} not found or inactive")
            return None

        token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
        if not token or not token.access_token:
            logger.warning(f"Offers worker: no token for account {ebay_account_id}")
            return None

        ebay_user_id = account.ebay_user_id or "unknown"

        # Ensure we have a sync state row
        state = get_or_create_sync_state(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="offers",
        )

        if not state.enabled:
            logger.info(f"Offers worker: sync disabled for account={ebay_account_id}")
            return None

        # Acquire run lock
        run = start_run(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="offers",
        )
        if not run:
            # Another fresh run is already in progress
            return None

        run_id = run.id
        sync_run_id = f"worker_offers_{run_id}"

        # Determine window using cursor + overlap
        overlap_minutes = OVERLAP_MINUTES_DEFAULT
        initial_backfill_days = INITIAL_BACKFILL_DAYS_DEFAULT

        from app.services.ebay_workers.state import compute_sync_window

        window_from, window_to = compute_sync_window(
            state,
            overlap_minutes=overlap_minutes,
            initial_backfill_days=initial_backfill_days,
        )

        from_iso = window_from.replace(microsecond=0).isoformat() + "Z"
        to_iso = window_to.replace(microsecond=0).isoformat() + "Z"

        log_start(
            db,
            run_id=run_id,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="offers",
            window_from=from_iso,
            window_to=to_iso,
            limit=OFFERS_LIMIT,
        )

        ebay_service = EbayService()
        total_fetched = 0
        total_stored = 0

        start_time = time.time()
        try:
            user_id = account.org_id
            result = await ebay_service.sync_all_offers(
                user_id=user_id,
                access_token=token.access_token,
                run_id=sync_run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                window_from=from_iso,
                window_to=to_iso,
            )

            total_fetched = int(result.get("total_fetched", 0))
            total_stored = int(result.get("total_stored", 0))
            sync_run_id = str(result.get("run_id")) if result.get("run_id") else sync_run_id

            # Worker-level page summary
            log_page(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="offers",
                page=1,
                fetched=total_fetched,
                stored=total_stored,
                offset=0,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            log_done(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="offers",
                total_fetched=total_fetched,
                total_stored=total_stored,
                duration_ms=duration_ms,
            )

            # Advance cursor to window_to (underlying sync uses this window for filtering)
            mark_sync_run_result(db, state, cursor_value=to_iso, error=None)

            complete_run(
                db,
                run,
                summary={
                    "total_fetched": total_fetched,
                    "total_stored": total_stored,
                    "duration_ms": duration_ms,
                    "window_from": from_iso,
                    "window_to": to_iso,
                    "sync_run_id": sync_run_id,
                },
            )

            return run_id

        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            msg = str(exc)
            log_error(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="offers",
                message=msg,
                stage="offers_worker",
            )
            mark_sync_run_result(db, state, cursor_value=None, error=msg)
            fail_run(
                db,
                run,
                error_message=msg,
                summary={
                    "total_fetched": total_fetched,
                    "total_stored": total_stored,
                    "duration_ms": duration_ms,
                    "sync_run_id": sync_run_id,
                },
            )
            logger.error(f"Offers worker for account={ebay_account_id} failed: {msg}")
            return run_id

    finally:
        db.close()