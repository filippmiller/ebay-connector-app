from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount
from app.models_sqlalchemy.ebay_workers import EbaySyncState
from app.services.ebay_account_service import ebay_account_service
from app.utils.logger import logger

from .state import are_workers_globally_enabled, get_or_create_sync_state
from .orders_worker import run_orders_worker_for_account
from .transactions_worker import run_transactions_worker_for_account
from .offers_worker import run_offers_worker_for_account
from .messages_worker import run_messages_worker_for_account
from .active_inventory_worker import run_active_inventory_worker_for_account


API_FAMILIES = [
    "orders",
    "transactions",
    "offers",
    "messages",
    "active_inventory",
]
def _get_db() -> Session:
    return SessionLocal()


async def run_cycle_for_account(ebay_account_id: str) -> None:
    """Run one sync cycle for all enabled workers for a single account.

    For now, only the Orders worker is wired. Additional API families can be
    added to API_FAMILIES and handled here.
    """

    db = _get_db()
    try:
        if not are_workers_globally_enabled(db):
            logger.info("Worker cycle skipped – global workers_enabled=false")
            return

        account: EbayAccount | None = ebay_account_service.get_account(db, ebay_account_id)
        if not account or not account.is_active:
            logger.info(f"Worker cycle: account {ebay_account_id} not found or inactive")
            return

        ebay_user_id = account.ebay_user_id or "unknown"

        # Ensure we have state rows for known API families
        for api_family in API_FAMILIES:
            get_or_create_sync_state(
                db,
                ebay_account_id=ebay_account_id,
                ebay_user_id=ebay_user_id,
                api_family=api_family,
            )

        # Orders worker
        state_orders: EbaySyncState | None = (
            db.query(EbaySyncState)
            .filter(
                EbaySyncState.ebay_account_id == ebay_account_id,
                EbaySyncState.api_family == "orders",
            )
            .first()
        )
        if state_orders and state_orders.enabled:
            await run_orders_worker_for_account(ebay_account_id)

        # Transactions worker
        state_tx: EbaySyncState | None = (
            db.query(EbaySyncState)
            .filter(
                EbaySyncState.ebay_account_id == ebay_account_id,
                EbaySyncState.api_family == "transactions",
            )
            .first()
        )
        if state_tx and state_tx.enabled:
            await run_transactions_worker_for_account(ebay_account_id)

        # Offers worker
        state_offers: EbaySyncState | None = (
            db.query(EbaySyncState)
            .filter(
                EbaySyncState.ebay_account_id == ebay_account_id,
                EbaySyncState.api_family == "offers",
            )
            .first()
        )
        if state_offers and state_offers.enabled:
            await run_offers_worker_for_account(ebay_account_id)

        # Messages worker
        state_messages: EbaySyncState | None = (
            db.query(EbaySyncState)
            .filter(
                EbaySyncState.ebay_account_id == ebay_account_id,
                EbaySyncState.api_family == "messages",
            )
            .first()
        )
        if state_messages and state_messages.enabled:
            await run_messages_worker_for_account(ebay_account_id)

        # Active Inventory snapshot worker
        state_active_inv: EbaySyncState | None = (
            db.query(EbaySyncState)
            .filter(
                EbaySyncState.ebay_account_id == ebay_account_id,
                EbaySyncState.api_family == "active_inventory",
            )
            .first()
        )
        if state_active_inv and state_active_inv.enabled:
            await run_active_inventory_worker_for_account(ebay_account_id)

    finally:
        db.close()


async def run_cycle_for_all_accounts() -> None:
    """Run one sync cycle for all *active* eBay accounts.

    This is the core entry point used by the background scheduler loop. It is
    safe to call from an external cron as well (e.g. Railway/Cloudflare).
    """

    db = _get_db()
    try:
        if not are_workers_globally_enabled(db):
            logger.info("Global workers_enabled=false – skipping cycle for all accounts")
            return

        # Fetch all active ebay accounts. Each account will have its own set of
        # worker sync states (orders, transactions, offers, messages, etc.).
        accounts: List[EbayAccount] = (
            db.query(EbayAccount)
            .filter(EbayAccount.is_active == True)  # noqa: E712
            .all()
        )
        if not accounts:
            logger.info("No active eBay accounts found – skipping worker cycle")
            return
    finally:
        db.close()

    for account in accounts:
        try:
            logger.info(
                "Running worker cycle for account id=%s ebay_user_id=%s house_name=%s",
                account.id,
                getattr(account, "ebay_user_id", "unknown"),
                getattr(account, "house_name", None),
            )
            await run_cycle_for_account(account.id)
        except Exception as exc:
            logger.error(
                "Worker cycle failed for account id=%s: %s",
                account.id,
                exc,
                exc_info=True,
            )
