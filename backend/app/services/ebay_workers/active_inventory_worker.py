from __future__ import annotations

import time
from datetime import datetime, timezone
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


ACTIVE_INV_LIMIT_DEFAULT = 0  # snapshot – no paging window
INITIAL_BACKFILL_DAYS_DEFAULT = 0  # not used for snapshot, but kept for symmetry


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_active_inventory_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Active Inventory snapshot worker for a specific eBay account.

    This worker triggers EbayService.sync_active_inventory_report, which uses the
    Sell Feed LMS_ACTIVE_INVENTORY_REPORT to obtain a full snapshot of all
    currently active listings for the account and stores them in the
    ebay_active_inventory table.

    The worker is wired into the generic ebay_workers scheduler and respects the
    per-account EbaySyncState.enabled flag for api_family="active_inventory".
    """

    db: Session = SessionLocal()
    try:
        account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.warning(f"ActiveInventory worker: account {ebay_account_id} not found or inactive")
            return None

        token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
        if not token or not token.access_token:
            logger.warning(f"ActiveInventory worker: no token for account {ebay_account_id}")
            return None

        ebay_user_id = account.ebay_user_id or "unknown"

        # Ensure we have a sync state row for api_family="active_inventory"
        state = get_or_create_sync_state(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="active_inventory",
        )

        if not state.enabled:
            logger.info(f"ActiveInventory worker: sync disabled for account={ebay_account_id}")
            return None

        # Acquire run lock
        run = start_run(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="active_inventory",
        )
        if not run:
            # Another fresh run is already in progress
            return None

        run_id = run.id
        sync_run_id = f"worker_active_inventory_{run_id}"

        # Snapshot worker does not use a date window; we still log a synthetic
        # window purely for observability.
        now = _now_utc()
        from_iso = now.replace(microsecond=0).isoformat() + "Z"
        to_iso = from_iso

        log_start(
            db,
            run_id=run_id,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="active_inventory",
            window_from=from_iso,
            window_to=to_iso,
            limit=ACTIVE_INV_LIMIT_DEFAULT,
        )

        ebay_service = EbayService()
        total_fetched = 0
        total_stored = 0

        start_time = time.time()
        try:
            user_id = account.org_id
            result = await ebay_service.sync_active_inventory_report(
                user_id=user_id,
                access_token=token.access_token,
                run_id=sync_run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
            )

            total_fetched = int(result.get("total_fetched", 0))
            total_stored = int(result.get("total_stored", 0))
            sync_run_id = str(result.get("run_id")) if result.get("run_id") else sync_run_id

            # Worker-level summary is represented as a single logical page
            log_page(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="active_inventory",
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
                api_family="active_inventory",
                total_fetched=total_fetched,
                total_stored=total_stored,
                duration_ms=duration_ms,
            )

            # For snapshots we simply record the last successful run time in the
            # cursor_value; consumers can use this as a "last updated" marker.
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
                api_family="active_inventory",
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
                api_family="active_inventory",
                message=msg,
                stage="active_inventory_worker",
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
                api_family="active_inventory",
                run_status="error",
                summary=error_summary,
            )
            logger.error(f"ActiveInventory worker for account={ebay_account_id} failed: {msg}")
            return run_id

    finally:
        db.close()
