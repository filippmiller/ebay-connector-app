from __future__ import annotations

import os
from typing import Optional, Any, Dict

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken, User
from app.services.ebay import EbayService
from app.utils.logger import logger
from app.config import settings
from .base_worker import BaseWorker


# Diagnostic flag - set EBAY_DEBUG_TRANSACTIONS=1 to enable verbose logging
_DEBUG_TRANSACTIONS = os.getenv("EBAY_DEBUG_TRANSACTIONS", "0") == "1"


class TransactionsWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="transactions",
            overlap_minutes=30,
            initial_backfill_days=90,
            limit=200,
        )

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
        ebay_service = EbayService()
        user_id = account.org_id

        # Fetch user to get environment
        user = db.query(User).filter(User.id == user_id).first()
        environment = user.ebay_environment if user else "sandbox"

        # Diagnostic logging
        if _DEBUG_TRANSACTIONS:
            token_prefix = token.access_token[:20] if token.access_token else "<none>"
            logger.info(
                "[TRANSACTIONS_WORKER_DEBUG] account_id=%s ebay_user_id=%s user_id=%s "
                "user.ebay_environment=%s resolved_environment=%s "
                "settings.EBAY_ENVIRONMENT=%s token_prefix=%s... "
                "window_from=%s window_to=%s",
                account.id,
                account.ebay_user_id,
                user_id,
                user.ebay_environment if user else "<no_user>",
                environment,
                settings.EBAY_ENVIRONMENT,
                token_prefix,
                window_from,
                window_to,
            )

        # Always log key environment info at INFO level for observability
        logger.info(
            "[transactions_worker] Starting sync for account=%s environment=%s (global=%s)",
            account.id,
            environment,
            settings.EBAY_ENVIRONMENT,
        )

        result = await ebay_service.sync_all_transactions(
            user_id=user_id,
            access_token=token.access_token,
            run_id=sync_run_id,
            ebay_account_id=account.id,
            ebay_user_id=account.ebay_user_id,
            window_from=window_from,
            window_to=window_to,
            environment=environment,
        )

        # Log success/failure summary
        total_fetched = result.get("total_fetched", 0)
        total_stored = result.get("total_stored", 0)
        error_msg = result.get("error_message") or result.get("error")
        if error_msg:
            logger.warning(
                "[transactions_worker] Completed with error for account=%s: fetched=%s stored=%s error=%s",
                account.id, total_fetched, total_stored, error_msg[:200] if error_msg else None,
            )
        else:
            logger.info(
                "[transactions_worker] Completed successfully for account=%s: fetched=%s stored=%s",
                account.id, total_fetched, total_stored,
            )

        return result


async def run_transactions_worker_for_account(
    ebay_account_id: str,
    triggered_by: str = "unknown",
) -> Optional[str]:
    """Run Transactions sync worker for a specific eBay account.
    
    Args:
        ebay_account_id: UUID of the eBay account
        triggered_by: How this run was triggered ("manual", "scheduler", or "unknown")
    """
    worker = TransactionsWorker()
    return await worker.run_for_account(ebay_account_id, triggered_by=triggered_by)
