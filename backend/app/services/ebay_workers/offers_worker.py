from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.models_sqlalchemy import SessionLocal
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay_offers_service import ebay_offers_service
from app.utils.logger import logger

from .state import get_or_create_sync_state, mark_sync_run_result
from .runs import start_run, complete_run, fail_run
from .logger import log_start, log_page, log_done, log_error
from .notifications import create_worker_run_notification


OFFERS_LIMIT = 100


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_offers_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Offers sync worker for a specific eBay account.

    Uses ebay_offers_service to fetch and store inventory offers and history.
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

        log_start(
            db,
            run_id=run_id,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="offers",
            window_from=None, # Offers sync is full snapshot, no window
            window_to=None,
            limit=OFFERS_LIMIT,
        )

        total_fetched = 0
        total_stored = 0
        total_events = 0

        start_time = time.time()
        try:
            # Use the new service
            stats = await ebay_offers_service.sync_offers_for_account(db, account)
            
            total_fetched = stats.get("fetched", 0)
            total_stored = stats.get("created", 0) + stats.get("updated", 0)
            total_events = stats.get("events", 0)
            
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

            # Update cursor to now (just for reference, as we do full sync)
            mark_sync_run_result(db, state, cursor_value=_now_utc().isoformat(), error=None)

            summary = {
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "total_events": total_events,
                "duration_ms": duration_ms,
            }

            complete_run(
                db,
                run,
                summary=summary,
            )

            create_worker_run_notification(
                db,
                account=account,
                api_family="offers",
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
                api_family="offers",
                message=msg,
                stage="offers_worker",
            )
            mark_sync_run_result(db, state, cursor_value=None, error=msg)
            error_summary = {
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "duration_ms": duration_ms,
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
                api_family="offers",
                run_status="error",
                summary=error_summary,
            )
            logger.error(f"Offers worker for account={ebay_account_id} failed: {msg}")
            return run_id

    finally:
        db.close()