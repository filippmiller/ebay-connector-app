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
from .runs import start_run, complete_run, fail_run, heartbeat
from .logger import log_start, log_page, log_done, log_error


ORDERS_LIMIT = 200
OVERLAP_MINUTES_DEFAULT = 60
INITIAL_BACKFILL_DAYS_DEFAULT = 90


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_orders_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Orders sync worker for a specific eBay account.

    This is the main entry point used by the scheduler and the manual "Run now"
    endpoint. It performs a safe windowed sync with overlap and upserts all
    orders into the existing orders tables via EbayService.

    Returns the run_id if a run was started, or None if a run was skipped
    because another active run is already in progress.
    """

    db: Session = SessionLocal()
    try:
        account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.warning(f"Orders worker: account {ebay_account_id} not found or inactive")
            return None

        # Load token for this account
        token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
        if not token or not token.access_token:
            logger.warning(f"Orders worker: no token for account {ebay_account_id}")
            return None

        ebay_user_id = account.ebay_user_id or "unknown"

        # Ensure we have a sync state row
        state = get_or_create_sync_state(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="orders",
        )

        if not state.enabled:
            logger.info(f"Orders worker: sync disabled for account={ebay_account_id}")
            return None

        # Acquire run lock
        run = start_run(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="orders",
        )
        if not run:
            # Another fresh run is already in progress
            return None

        run_id = run.id
        # Use a deterministic sync_event run_id so we can attach the terminal UI
        sync_run_id = f"worker_orders_{run_id}"

        # Determine window using cursor + overlap
        overlap_minutes = OVERLAP_MINUTES_DEFAULT
        initial_backfill_days = INITIAL_BACKFILL_DAYS_DEFAULT

        # Compute incremental window (cursor minus overlap, or initial backfill)
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
            api_family="orders",
            window_from=from_iso,
            window_to=to_iso,
            limit=ORDERS_LIMIT,
        )

        ebay_service = EbayService()

        total_fetched = 0
        total_stored = 0

        # For now we reuse the existing sync_all_orders implementation which
        # already performs full paging and upserts. We call it for the account's
        # owning user (org_id) and rely on its internal logging for detailed
        # progress. The worker log records a high-level summary.
        start_time = time.time()
        try:
            # sync_all_orders expects the org/user id and an access token.
            # We reuse the account.org_id as the logical user_id and pass
            # the account token so the sync reuses the same HTTP + DB logic
            # as the manual "Sync Data" operations.
            user_id = account.org_id
            result = await ebay_service.sync_all_orders(
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
            # Prefer the run_id returned by sync_all_orders, but fall back to
            # our deterministic value in case of older implementations.
            sync_run_id = str(result.get("run_id")) if result.get("run_id") else sync_run_id

            # For the worker-level log we treat the entire call as a single page
            log_page(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="orders",
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
                api_family="orders",
                total_fetched=total_fetched,
                total_stored=total_stored,
                duration_ms=duration_ms,
            )

            # Advance cursor to window_to (safe because sync_all_orders fetches all
            # recent orders with its own 90-day window). The overlap logic will
            # still refetch some orders next time, but upserts keep it idempotent.
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
                api_family="orders",
                message=msg,
                stage="orders_worker",
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
            logger.error(f"Orders worker for account={ebay_account_id} failed: {msg}")
            return run_id

    finally:
        db.close()
