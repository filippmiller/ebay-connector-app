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
from .notifications import create_worker_run_notification


FINANCES_LIMIT = 200
# 30-minute overlap for consistent cursor behaviour across workers.
OVERLAP_MINUTES_DEFAULT = 30
INITIAL_BACKFILL_DAYS_DEFAULT = 90


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_finances_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Finances transactions sync worker for a specific eBay account.

    This mirrors the Transactions worker but writes into the dedicated
    ``ebay_finances_transactions`` / ``ebay_finances_fees`` tables via
    ``EbayService.sync_finances_transactions``.

    Returns the worker run_id if a run was started, or None if skipped
    (disabled, missing token, or another fresh run in progress).
    """

    db: Session = SessionLocal()
    try:
        account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.warning(
                "Finances worker: account %s not found or inactive", ebay_account_id
            )
            return None

        # Load token for this account
        token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
        if not token or not token.access_token:
            logger.warning("Finances worker: no token for account %s", ebay_account_id)
            return None

        ebay_user_id = account.ebay_user_id or "unknown"

        # Ensure we have a sync state row
        state = get_or_create_sync_state(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="finances",
        )

        if not state.enabled:
            logger.info("Finances worker: sync disabled for account=%s", ebay_account_id)
            return None

        # Acquire run lock
        run = start_run(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="finances",
        )
        if not run:
            # Another fresh run is already in progress
            return None

        run_id = run.id
        # Use a deterministic sync_event run_id so we can attach the terminal UI
        sync_run_id = f"worker_finances_{run_id}"

        # Determine window using cursor + overlap
        overlap_minutes = OVERLAP_MINUTES_DEFAULT
        initial_backfill_days = INITIAL_BACKFILL_DAYS_DEFAULT

        from app.services.ebay_workers.state import compute_sync_window

        window_from, window_to = compute_sync_window(
            state,
            overlap_minutes=overlap_minutes,
            initial_backfill_days=initial_backfill_days,
        )

        # Format timestamps as proper UTC ISO8601 strings ending with "Z".
        # We intentionally avoid producing values like "+00:00Z" which break
        # downstream parsing in EbayService.sync_finances_transactions.
        from_iso = window_from.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        to_iso = window_to.replace(microsecond=0).isoformat().replace("+00:00", "Z")

        log_start(
            db,
            run_id=run_id,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="finances",
            window_from=from_iso,
            window_to=to_iso,
            limit=FINANCES_LIMIT,
        )

        ebay_service = EbayService()
        total_fetched = 0
        total_stored = 0

        start_time = time.time()
        try:
            # sync_finances_transactions expects the org/user id and an access token.
            user_id = account.org_id
            result = await ebay_service.sync_finances_transactions(
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

            # One logical "page" at worker level
            log_page(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="finances",
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
                api_family="finances",
                total_fetched=total_fetched,
                total_stored=total_stored,
                duration_ms=duration_ms,
            )

            # Advance cursor to window_to
            mark_sync_run_result(db, state, cursor_value=to_iso, error=None)

            summary = {
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "duration_ms": duration_ms,
                "window_from": from_iso,
                "window_to": to_iso,
                "sync_run_id": sync_run_id,
            }

            complete_run(
                db,
                run,
                summary=summary,
            )

            create_worker_run_notification(
                db,
                account=account,
                api_family="finances",
                run_status="completed",
                summary=summary,
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
                api_family="finances",
                message=msg,
                stage="finances_worker",
            )
            mark_sync_run_result(db, state, cursor_value=None, error=msg)
            error_summary = {
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "duration_ms": duration_ms,
                "window_from": from_iso,
                "window_to": to_iso,
                "sync_run_id": sync_run_id,
                "error_message": msg,
            }
            fail_run(
                db,
                run,
                error_message=msg,
                summary=error_summary,
            )
            create_worker_run_notification(
                db,
                account=account,
                api_family="finances",
                run_status="error",
                summary=error_summary,
            )
            logger.error("Finances worker for account=%s failed: %s", ebay_account_id, msg)
            return run_id

    finally:
        db.close()
