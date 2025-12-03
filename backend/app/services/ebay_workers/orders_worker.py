from __future__ import annotations

from typing import Optional, Any, Dict

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.services.ebay import EbayService
from .base_worker import BaseWorker


class OrdersWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="orders",
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
        # sync_all_orders expects the org/user id and an access token.
        # We reuse the account.org_id as the logical user_id and pass
        # the account token so the sync reuses the same HTTP + DB logic
        # as the manual "Sync Data" operations.
        user_id = account.org_id

        result = await ebay_service.sync_all_orders(
            user_id=user_id,
            access_token=token.access_token,
            run_id=sync_run_id,
            ebay_account_id=account.id,
            ebay_user_id=account.ebay_user_id,
            window_from=window_from,
            window_to=window_to,
        )
        return result


async def run_orders_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Orders sync worker for a specific eBay account."""
    worker = OrdersWorker()
    return await worker.run_for_account(ebay_account_id)
