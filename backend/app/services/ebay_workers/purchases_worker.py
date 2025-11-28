from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken, EbayBuyer
from app.models_sqlalchemy import SessionLocal
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay import EbayService
from app.utils.logger import logger

from .state import get_or_create_sync_state, mark_sync_run_result
from .runs import start_run, complete_run, fail_run
from .logger import log_start, log_page, log_done, log_error
from .notifications import create_worker_run_notification


PURCHASES_LIMIT = 500
OVERLAP_MINUTES_DEFAULT = 30
INITIAL_BACKFILL_DAYS_DEFAULT = 30


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def run_purchases_worker_for_account(ebay_account_id: str) -> Optional[str]:
    """Sync BUYING purchases for a single eBay account into ebay_buyer.

    This worker uses the Trading API via ``EbayService.get_purchases`` and stores
    the results in the Postgres-backed ``ebay_buyer`` table. It is driven by the
    generic worker sync state (``ebay_sync_state``) with api_family="buyer".
    """

    db: Session = SessionLocal()
    try:
        account: Optional[EbayAccount] = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.warning(f"Purchases worker: account {ebay_account_id} not found or inactive")
            return None

        token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
        if not token or not token.access_token:
            logger.warning(f"Purchases worker: no token for account {ebay_account_id}")
            return None

        ebay_user_id = account.ebay_user_id or "unknown"

        # Ensure we have a sync state row
        state = get_or_create_sync_state(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="buyer",
        )

        if not state.enabled:
            logger.info(f"Purchases worker: sync disabled for account={ebay_account_id}")
            return None

        # Acquire run lock
        run = start_run(
            db,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
            api_family="buyer",
        )
        if not run:
            # Another fresh run is already in progress
            return None

        run_id = run.id
        # Use a deterministic sync_event run_id so the SyncTerminal can attach
        # to this worker even while it is still running.
        sync_run_id = f"worker_buyer_{run_id}"

        # Determine window using cursor + overlap
        overlap_minutes = OVERLAP_MINUTES_DEFAULT
        initial_backfill_days = INITIAL_BACKFILL_DAYS_DEFAULT

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
            api_family="buyer",
            window_from=from_iso,
            window_to=to_iso,
            limit=PURCHASES_LIMIT,
        )

        ebay_service = EbayService()

        # Wire into the generic SyncEventLogger so the workers terminal can
        # stream live progress (start → progress → done/error) for this worker.
        from app.services.sync_event_logger import SyncEventLogger

        user_id = account.org_id
        event_logger = SyncEventLogger(user_id, "buyer", run_id=sync_run_id)

        total_fetched = 0
        total_stored = 0

        start_time = time.time()
        try:
            event_logger.log_start(
                "Starting Buyer purchases sync for worker window "
                f"{from_iso}..{to_iso} (account={ebay_account_id})"
            )
            # For purchases, we call a per-account helper and do ORM upserts here.
            since_dt = window_from
            purchases = await ebay_service.get_purchases(
                access_token=token.access_token,
                since=since_dt,
            )

            total_fetched = len(purchases)
            event_logger.log_info(
                f"Fetched {total_fetched} purchases from Buying API for account={ebay_account_id}",
                extra_data={
                    "window_from": from_iso,
                    "window_to": to_iso,
                },
            )

            # Upsert into ebay_buyer, preserving warehouse-driven fields.
            stored = 0
            for dto in purchases:
                # dto is expected to be a dict-like object with ebay_buyer-compatible keys.
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
                    # External, API-driven fields we are allowed to refresh
                    external_fields = [
                        "title",
                        "shipping_carrier",
                        "tracking_number",
                        "buyer_checkout_message",
                        "condition_display_name",
                        "seller_email",
                        "seller_id",
                        "seller_site",
                        "seller_location",
                        "quantity_purchased",
                        "current_price",
                        "shipping_service_cost",
                        "total_price",
                        "total_transaction_price",
                        "payment_hold_status",
                        "buyer_paid_status",
                        "paid_time",
                        "shipped_time",
                        "platform",
                        "buyer_id",
                        "item_url",
                        "gallery_url",
                        "description",
                        "private_notes",
                        "refund_flag",
                        "refund_amount",
                    ]
                    for field in external_fields:
                        if field in dto:
                            setattr(existing, field, dto[field])

                    existing.record_updated_at = _now_utc()
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
                        record_created_at=_now_utc(),
                        record_created_by="purchases_worker",
                    )
                    db.add(obj)
                    stored += 1

            db.commit()
            total_stored = stored

            # Emit a single progress event with a 100% bar so the terminal
            # shows clear completion information for this worker run.
            event_logger.log_progress(
                "Upserted Buyer purchases into ebay_buyer",
                current_page=1,
                total_pages=1,
                items_fetched=total_fetched,
                items_stored=total_stored,
            )

            # One logical "page" at worker level
            log_page(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="buyer",
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
                api_family="buyer",
                total_fetched=total_fetched,
                total_stored=total_stored,
                duration_ms=duration_ms,
            )

            event_logger.log_done(
                "Buyer purchases sync completed",
                total_fetched,
                total_stored,
                duration_ms,
            )

            # Advance cursor to window_to (we maintain an overlap window so this is safe)
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
                api_family="buyer",
                run_status="completed",
                summary=summary,
            )

            logger.info(
                "Purchases worker completed for account=%s: fetched=%s stored=%s window=%s..%s",
                ebay_account_id,
                total_fetched,
                total_stored,
                from_iso,
                to_iso,
            )

            return run_id

        except Exception as exc:  # noqa: BLE001
            # Ensure the session is usable again after a failed DB operation.
            try:
                db.rollback()
            except Exception:
                # If rollback itself fails, we still want to capture the original error.
                pass

            duration_ms = int((time.time() - start_time) * 1000)
            msg = str(exc)

            event_logger.log_error(
                f"Buyer purchases worker failed: {msg}",
                error=exc,
                extra_data={
                    "ebay_account_id": ebay_account_id,
                    "window_from": from_iso,
                    "window_to": to_iso,
                },
            )

            log_error(
                db,
                run_id=run_id,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family="buyer",
                message=msg,
                stage="purchases_worker",
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
                api_family="buyer",
                run_status="error",
                summary=error_summary,
            )
            logger.error(f"Purchases worker for account={ebay_account_id} failed: {msg}")
            return run_id

        finally:
            # Always release SyncEventLogger resources
            event_logger.close()

    finally:
        db.close()
