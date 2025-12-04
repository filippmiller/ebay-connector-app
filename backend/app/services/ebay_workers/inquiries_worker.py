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


INQUIRIES_OVERLAP_MINUTES_DEFAULT = 30
INQUIRIES_INITIAL_BACKFILL_DAYS_DEFAULT = 90


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_inquiries_worker_for_account(
    ebay_account_id: str,
    triggered_by: str = "unknown",
) -> Optional[str]:
    """Run Post-Order Inquiries worker for a specific eBay account.

    This worker syncs buyer inquiries (pre-case disputes) via
    ``EbayService.sync_postorder_inquiries`` into the ebay_inquiries table. The
    unified Cases grid then joins ebay_inquiries, ebay_cases, and ebay_disputes
    into a single view.
    
    Args:
        ebay_account_id: UUID of the eBay account
        triggered_by: How this run was triggered ("manual", "scheduler", or "unknown")
    """

    db: Session = SessionLocal()
    try:
        account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.warning(f"Inquiries worker: account {ebay_account_id} not found or inactive")
            return None

        # Use the unified token provider
        from app.services.ebay_token_provider import get_valid_access_token
        
        token_result = await get_valid_access_token(
            db,
            ebay_account_id,
            api_family="inquiries",
            triggered_by=f"worker_{triggered_by}",
        )
        
        if not token_result.success:
            logger.warning(
                f"Inquiries worker: token retrieval failed for account {ebay_account_id}: "
                f"{token_result.error_code} - {token_result.error_message}"
            )
            return None

        # CRITICAL: Use decrypted token from token_result, not token.access_token
        # token.access_token may return ENC:v1:... if decryption fails
        decrypted_access_token = token_result.access_token
        if not decrypted_access_token:
            logger.warning(f"Inquiries worker: no decrypted access token for account {ebay_account_id}")
            return None
        
        # Validate token is decrypted
        if decrypted_access_token.startswith("ENC:"):
            logger.error(
                f"[inquiries_worker] ⚠️ TOKEN STILL ENCRYPTED! account={ebay_account_id} "
                f"token_hash={token_result.token_hash}. Check SECRET_KEY/JWT_SECRET in worker environment."
            )
            return None
        
        logger.info(
            f"[inquiries_worker] Token retrieved: account={ebay_account_id} "
            f"source={token_result.source} token_hash={token_result.token_hash} triggered_by={triggered_by} "
            f"token_prefix={decrypted_access_token[:15]}..."
        )

        ebay_user_id = account.ebay_user_id or "unknown"

        state = get_or_create_sync_state(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="inquiries",
        )

        if not state.enabled:
            logger.info(f"Inquiries worker: sync disabled for account={ebay_account_id}")
            return None

        # Acquire run lock
        run = start_run(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="inquiries",
        )
        if not run:
            return None

        run_id = run.id
        sync_run_id = f"worker_inquiries_{run_id}"

        overlap_minutes = INQUIRIES_OVERLAP_MINUTES_DEFAULT
        initial_backfill_days = INQUIRIES_INITIAL_BACKFILL_DAYS_DEFAULT

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
            api_family="inquiries",
            window_from=from_iso,
            window_to=to_iso,
            limit=None,
        )

        ebay_service = EbayService()
        total_fetched = 0
        total_stored = 0

        start_time = time.time()
        try:
            user_id = account.org_id

            result = await ebay_service.sync_postorder_inquiries(
                user_id=user_id,
                access_token=decrypted_access_token,  # Use decrypted token from token_result
                run_id=sync_run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                window_from=from_iso,
                window_to=to_iso,
            )

            total_fetched = int(result.get("total_fetched", 0))
            total_stored = int(result.get("total_stored", 0))

            log_page(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="inquiries",
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
                api_family="inquiries",
                total_fetched=total_fetched,
                total_stored=total_stored,
                duration_ms=duration_ms,
            )

            # Advance cursor to window_to; upserts keep duplicates safe.
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
                api_family="inquiries",
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
                api_family="inquiries",
                message=msg,
                stage="inquiries_worker",
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
                api_family="inquiries",
                run_status="error",
                summary=error_summary,
            )
            logger.error(f"Inquiries worker for account={ebay_account_id} failed: {msg}")
            return run_id

    finally:
        db.close()
