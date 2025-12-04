from __future__ import annotations

from typing import Optional, Any, Dict

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken, EbayBuyer
from app.services.ebay import EbayService
from app.services.sync_event_logger import SyncEventLogger
from app.services.ebay_event_inbox import log_ebay_event
from app.utils.logger import logger
from .base_worker import BaseWorker


class PurchasesWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="buyer",
            overlap_minutes=30,
            initial_backfill_days=30,
            limit=500,
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
        ebay_account_id = account.id
        ebay_user_id = account.ebay_user_id or "unknown"

        # Wire into the generic SyncEventLogger
        event_logger = SyncEventLogger(user_id, "buyer", run_id=sync_run_id)

        try:
            event_logger.log_start(
                "Starting Buyer purchases sync for worker window "
                f"{window_from}..{window_to} (account={ebay_account_id})"
            )

            purchases = await ebay_service.get_purchases(
                access_token=token.access_token,
                since=window_from,
            )

            total_fetched = len(purchases)
            event_logger.log_info(
                f"Fetched {total_fetched} purchases from Buying API for account={ebay_account_id}",
                extra_data={
                    "window_from": window_from,
                    "window_to": window_to,
                },
            )

            stored = 0
            for dto in purchases:
                item_id = dto.get("item_id")
                transaction_id = dto.get("transaction_id")
                order_line_item_id = dto.get("order_line_item_id")

                existing: Optional[EbayBuyer] = (
                    db.query(EbayBuyer)
                    .filter(
                        EbayBuyer.ebay_account_id == ebay_account_id,
                        EbayBuyer.item_id == item_id,
                        EbayBuyer.transaction_id == transaction_id,
                        EbayBuyer.order_line_item_id == order_line_item_id,
                    )
                    .one_or_none()
                )

                if existing:
                    # Update external fields
                    external_fields = [
                        "title", "shipping_carrier", "tracking_number", "buyer_checkout_message",
                        "condition_display_name", "seller_email", "seller_id", "seller_site",
                        "seller_location", "quantity_purchased", "current_price",
                        "shipping_service_cost", "total_price", "total_transaction_price",
                        "payment_hold_status", "buyer_paid_status", "paid_time", "shipped_time",
                        "platform", "buyer_id", "item_url", "gallery_url", "description",
                        "private_notes", "refund_flag", "refund_amount",
                    ]
                    for field in external_fields:
                        if field in dto:
                            setattr(existing, field, dto[field])

                    existing.record_updated_at = self._now_utc()
                    existing.record_updated_by = "purchases_worker"
                else:
                    obj = EbayBuyer(
                        ebay_account_id=ebay_account_id,
                        item_id=item_id,
                        transaction_id=transaction_id,
                        order_line_item_id=order_line_item_id,
                        title=dto.get("title"),
                        shipping_carrier=dto.get("shipping_carrier"),
                        tracking_number=dto.get("tracking_number"),
                        buyer_checkout_message=dto.get("buyer_checkout_message"),
                        condition_display_name=dto.get("condition_display_name"),
                        seller_email=dto.get("seller_email"),
                        seller_id=dto.get("seller_id"),
                        seller_site=dto.get("seller_site"),
                        seller_location=dto.get("seller_location"),
                        quantity_purchased=dto.get("quantity_purchased"),
                        current_price=dto.get("current_price"),
                        shipping_service_cost=dto.get("shipping_service_cost"),
                        total_price=dto.get("total_price"),
                        total_transaction_price=dto.get("total_transaction_price"),
                        payment_hold_status=dto.get("payment_hold_status"),
                        buyer_paid_status=dto.get("buyer_paid_status"),
                        paid_time=dto.get("paid_time"),
                        shipped_time=dto.get("shipped_time"),
                        platform=dto.get("platform"),
                        buyer_id=dto.get("buyer_id"),
                        item_url=dto.get("item_url"),
                        gallery_url=dto.get("gallery_url"),
                        description=dto.get("description"),
                        private_notes=dto.get("private_notes"),
                        refund_flag=dto.get("refund_flag"),
                        refund_amount=dto.get("refund_amount"),
                        record_created_at=self._now_utc(),
                        record_created_by="purchases_worker",
                    )
                    db.add(obj)
                    stored += 1

                # Log event
                try:
                    log_ebay_event(
                        source="trading_poll",
                        channel="buying_api",
                        topic="PURCHASE_UPDATED" if existing else "PURCHASE_CREATED",
                        entity_type="PURCHASE",
                        entity_id=transaction_id or order_line_item_id or item_id,
                        ebay_account=ebay_user_id,
                        event_time=self._now_utc(),
                        payload=dto,
                        db=db,
                        headers={
                            "worker": "purchases_worker",
                            "api_family": "buyer",
                            "user_id": user_id,
                            "ebay_account_id": ebay_account_id,
                        }
                    )
                except Exception:
                    logger.warning("Failed to log event for purchase %s", transaction_id, exc_info=True)

            db.commit()

            event_logger.log_progress(
                "Upserted Buyer purchases into ebay_buyer",
                current_page=1,
                total_pages=1,
                items_fetched=total_fetched,
                items_stored=stored,
            )
            
            # Calculate duration for event logger
            # Note: BaseWorker calculates its own duration for the main log
            
            event_logger.log_done(
                "Buyer purchases sync completed",
                total_fetched,
                stored,
                0, # Duration not easily available here without passing start time, but that's fine
            )

            return {
                "total_fetched": total_fetched,
                "total_stored": stored,
            }

        except Exception as exc:
            event_logger.log_error(
                f"Buyer purchases worker failed: {str(exc)}",
                error=exc,
                extra_data={
                    "ebay_account_id": ebay_account_id,
                    "window_from": window_from,
                    "window_to": window_to,
                },
            )
            raise
        finally:
            event_logger.close()


async def run_purchases_worker_for_account(
    ebay_account_id: str,
    triggered_by: str = "unknown",
) -> Optional[str]:
    """Sync BUYING purchases for a single eBay account into ebay_buyer."""
    worker = PurchasesWorker()
    return await worker.run_for_account(ebay_account_id, triggered_by=triggered_by)
