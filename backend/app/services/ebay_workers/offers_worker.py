from __future__ import annotations

from typing import Optional, Any, Dict

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.services.ebay_offers_service import ebay_offers_service
from .base_worker import BaseWorker


class OffersWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="offers",
            overlap_minutes=None,  # No window, full snapshot
            initial_backfill_days=90,
            limit=100,
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
        # Use the new service, passing the safely decrypted token
        # CRITICAL: Use helper to safely get decrypted token
        access_token = self._get_decrypted_token(token, account.id)
        if not access_token:
            return {
                "total_fetched": 0,
                "total_stored": 0,
                "error_message": "Access token unavailable or encrypted",
            }
            
        stats = await ebay_offers_service.sync_offers_for_account(db, account, access_token=access_token)

        return {
            "total_fetched": stats.get("fetched", 0),
            "total_stored": stats.get("created", 0) + stats.get("updated", 0),
            "total_events": stats.get("events", 0),
            **stats,
        }


async def run_offers_worker_for_account(
    ebay_account_id: str,
    triggered_by: str = "unknown",
) -> Optional[str]:
    """Run Offers sync worker for a specific eBay account."""
    worker = OffersWorker()
    return await worker.run_for_account(ebay_account_id, triggered_by=triggered_by)