from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, Literal

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.models_sqlalchemy import SessionLocal
from app.services.ebay_account_service import ebay_account_service
from app.utils.logger import logger

from .state import get_or_create_sync_state, mark_sync_run_result, compute_sync_window
from .runs import start_run, complete_run, fail_run
from .logger import log_start, log_page, log_done, log_error
from .notifications import create_worker_run_notification


class BaseWorker:
    def __init__(
        self,
        api_family: str,
        overlap_minutes: Optional[int] = 30,
        initial_backfill_days: int = 90,
        limit: int = 200,
    ):
        self.api_family = api_family
        self.overlap_minutes = overlap_minutes
        self.initial_backfill_days = initial_backfill_days
        self.limit = limit
        # Track how this worker was triggered for logging
        self._triggered_by: Literal["manual", "scheduler", "unknown"] = "unknown"

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    async def execute_sync(
        self,
        db: Session,
        account: EbayAccount,
        token: EbayToken,
        run_id: str,
        sync_run_id: str,
        window_from: Optional[str],
        window_to: Optional[str],
    ) -> Dict[str, Any]:
        """
        Execute the actual sync logic.
        Must return a dictionary with:
        - total_fetched (int)
        - total_stored (int)
        - sync_run_id (str, optional)
        - any other stats
        """
        raise NotImplementedError

    async def run_for_account(
        self,
        ebay_account_id: str,
        triggered_by: Literal["manual", "scheduler", "unknown"] = "unknown",
    ) -> Optional[str]:
        """Run the worker for a specific eBay account.
        
        Args:
            ebay_account_id: UUID of the eBay account
            triggered_by: How this run was triggered ("manual", "scheduler", or "unknown")
        
        Returns:
            Run ID if started successfully, None if skipped
        """
        self._triggered_by = triggered_by
        db: Session = SessionLocal()
        try:
            account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
            if not account or not account.is_active:
                logger.warning(f"{self.api_family} worker: account {ebay_account_id} not found or inactive")
                return None

            # Use the unified token provider instead of direct DB access
            from app.services.ebay_token_provider import get_valid_access_token
            
            token_result = await get_valid_access_token(
                db,
                ebay_account_id,
                api_family=self.api_family,
                force_refresh=False,
                validate_with_identity_api=False,
                triggered_by=f"worker_{triggered_by}",
            )
            
            if not token_result.success:
                logger.warning(
                    f"{self.api_family} worker: token retrieval failed for account {ebay_account_id}: "
                    f"{token_result.error_code} - {token_result.error_message}"
                )
                return None
            
            # Get the token object for backward compatibility with execute_sync signature
            token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
            if not token or not token.access_token:
                logger.warning(f"{self.api_family} worker: no token for account {ebay_account_id}")
                return None
            
            # Log token info for debugging (never log raw token)
            logger.info(
                f"[{self.api_family}_worker] Token retrieved: account={ebay_account_id} "
                f"source={token_result.source} token_hash={token_result.token_hash} "
                f"environment={token_result.environment} triggered_by={triggered_by}"
            )

            ebay_user_id = account.ebay_user_id or "unknown"

            state = get_or_create_sync_state(
                db,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family=self.api_family,
            )

            if not state.enabled:
                logger.info(f"{self.api_family} worker: sync disabled for account={ebay_account_id}")
                return None

            run = start_run(
                db,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family=self.api_family,
            )
            if not run:
                # Another fresh run is already in progress
                return None

            run_id = run.id
            sync_run_id = f"worker_{self.api_family}_{run_id}"

            # Window calculation
            from_iso = None
            to_iso = None

            # If overlap_minutes is None, it means full sync (no window)
            if self.overlap_minutes is not None:
                window_from, window_to = compute_sync_window(
                    state,
                    overlap_minutes=self.overlap_minutes,
                    initial_backfill_days=self.initial_backfill_days,
                )

                MAX_WINDOW_HOURS = 24
                if (window_to - window_from).total_seconds() > (MAX_WINDOW_HOURS * 3600):
                    window_to = window_from + timedelta(hours=MAX_WINDOW_HOURS)

                # Format timestamps as proper UTC ISO8601 strings ending with "Z".
                from_iso = window_from.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                to_iso = window_to.replace(microsecond=0).isoformat().replace("+00:00", "Z")

            log_start(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family=self.api_family,
                window_from=from_iso,
                window_to=to_iso,
                limit=self.limit,
            )

            total_fetched = 0
            total_stored = 0
            start_time = time.time()

            try:
                stats = await self.execute_sync(
                    db, account, token, run_id, sync_run_id, from_iso, to_iso
                )

                total_fetched = int(stats.get("total_fetched", stats.get("fetched", 0)))
                total_stored = int(stats.get("total_stored", stats.get("stored", stats.get("created", 0) + stats.get("updated", 0))))
                sync_run_id = str(stats.get("sync_run_id", stats.get("run_id", sync_run_id)))

                duration_ms = int((time.time() - start_time) * 1000)

                # Log page (assuming single page for worker level log)
                log_page(
                    db,
                    run_id=run_id,
                    ebay_account_id=ebay_account_id,
                    ebay_user_id=ebay_user_id,
                    api_family=self.api_family,
                    page=1,
                    fetched=total_fetched,
                    stored=total_stored,
                    offset=0,
                )

                log_done(
                    db,
                    run_id=run_id,
                    ebay_account_id=ebay_account_id,
                    ebay_user_id=ebay_user_id,
                    api_family=self.api_family,
                    total_fetched=total_fetched,
                    total_stored=total_stored,
                    duration_ms=duration_ms,
                )

                # Update cursor
                new_cursor = to_iso if to_iso else self._now_utc().isoformat()
                mark_sync_run_result(db, state, cursor_value=new_cursor, error=None)

                summary = {
                    "total_fetched": total_fetched,
                    "total_stored": total_stored,
                    "duration_ms": duration_ms,
                    "window_from": from_iso,
                    "window_to": to_iso,
                    "sync_run_id": sync_run_id,
                }
                summary.update(stats)

                complete_run(db, run, summary=summary)

                create_worker_run_notification(
                    db,
                    account=account,
                    api_family=self.api_family,
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
                    api_family=self.api_family,
                    message=msg,
                    stage=f"{self.api_family}_worker",
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
                fail_run(db, run, error_message=msg, summary=error_summary)
                create_worker_run_notification(
                    db,
                    account=account,
                    api_family=self.api_family,
                    run_status="error",
                    summary=error_summary,
                )
                logger.error(f"{self.api_family} worker for account={ebay_account_id} failed: {msg}")
                return run_id

        finally:
            db.close()
