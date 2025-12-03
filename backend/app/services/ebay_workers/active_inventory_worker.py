from __future__ import annotations

from typing import Optional, Any, Dict

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.services.ebay import EbayService
from .base_worker import BaseWorker


class ActiveInventoryWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="active_inventory",
            overlap_minutes=None,  # No window, full snapshot
            initial_backfill_days=0,
            limit=0,
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

        result = await ebay_service.sync_active_inventory_report(
            user_id=user_id,
            access_token=token.access_token,
            run_id=sync_run_id,
            ebay_account_id=account.id,
            ebay_user_id=account.ebay_user_id,
        )
        return result


async def run_active_inventory_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Run Active Inventory snapshot worker for a specific eBay account."""
    worker = ActiveInventoryWorker()
    return await worker.run_for_account(ebay_account_id)
