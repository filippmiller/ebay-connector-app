from __future__ import annotations

from typing import List
import random

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
from .purchases_worker import run_purchases_worker_for_account
from .cases_worker import run_cases_worker_for_account
from .inquiries_worker import run_inquiries_worker_for_account
from .finances_worker import run_finances_worker_for_account
from .messages_worker import run_messages_worker_for_account
from .offers_worker import run_offers_worker_for_account
from .transactions_worker import run_transactions_worker_for_account
from .orders_worker import run_orders_worker_for_account
from .active_inventory_worker import run_active_inventory_worker_for_account
from .returns_worker import run_returns_worker_for_account


from app.services.ebay_token_refresh_service import run_token_refresh_job

API_FAMILIES = [
    "orders",
    "transactions",
    "offers",
    "messages",
    "active_inventory",
    # Buyer/purchases (legacy tbl_ebay_buyer equivalent)
    "buyer",
    # Post-Order disputes stack
    "cases",
    "inquiries",
    "finances",
    # New Post-Order Returns worker
    "returns",
]

def _get_db() -> Session:
    return SessionLocal()


async def run_cycle_for_account(ebay_account_id: str) -> None:
    """Run one sync cycle for all enabled workers for a single account.

    Runs workers in parallel using asyncio.gather to prevent one slow worker
    from blocking others for the same account.
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

        # Collect all enabled worker tasks
        tasks = []

        # Helper to check state and add task
        def _add_if_enabled(api_family: str, worker_func):
            state: EbaySyncState | None = (
                db.query(EbaySyncState)
                .filter(
                    EbaySyncState.ebay_account_id == ebay_account_id,
                    EbaySyncState.api_family == api_family,
                )
                .first()
            )
            if state and state.enabled:
                logger.info(f"Scheduling {api_family} worker for account {ebay_account_id}")
                tasks.append(worker_func(ebay_account_id))
            else:
                logger.info(f"Skipping {api_family} worker for account {ebay_account_id} (disabled)")

        # All workers are triggered by scheduler in this context
        triggered_by = "scheduler"
        
        # 1. Orders
        _add_if_enabled("orders", lambda aid: run_orders_worker_for_account(aid, triggered_by=triggered_by))
        
        # 2. Transactions
        _add_if_enabled("transactions", lambda aid: run_transactions_worker_for_account(aid, triggered_by=triggered_by))
        
        # 3. Offers
        _add_if_enabled("offers", lambda aid: run_offers_worker_for_account(aid, triggered_by=triggered_by))
        
        # 4. Messages
        _add_if_enabled("messages", lambda aid: run_messages_worker_for_account(aid, triggered_by=triggered_by))
        
        # 5. Active Inventory
        _add_if_enabled("active_inventory", lambda aid: run_active_inventory_worker_for_account(aid, triggered_by=triggered_by))
        
        # 6. Buyer/Purchases
        _add_if_enabled("buyer", lambda aid: run_purchases_worker_for_account(aid, triggered_by=triggered_by))
        
        # 7. Cases
        _add_if_enabled("cases", lambda aid: run_cases_worker_for_account(aid, triggered_by=triggered_by))
        
        # 8. Inquiries
        _add_if_enabled("inquiries", lambda aid: run_inquiries_worker_for_account(aid, triggered_by=triggered_by))
        
        # 9. Finances
        _add_if_enabled("finances", lambda aid: run_finances_worker_for_account(aid, triggered_by=triggered_by))
        
        # 10. Returns
        _add_if_enabled("returns", lambda aid: run_returns_worker_for_account(aid, triggered_by=triggered_by))

        if tasks:
            import asyncio
            # Run all enabled workers for this account in parallel
            await asyncio.gather(*tasks, return_exceptions=True)

    finally:
        db.close()


async def run_cycle_for_all_accounts() -> None:
    """Run one sync cycle for all *active* eBay accounts.

    Runs accounts in parallel with a concurrency limit to avoid overloading
    the database or API rate limits.
    """
    import asyncio

    db = _get_db()
    try:
        # 1. Refresh tokens first to ensure workers don't fail with 401
        logger.info("Running token refresh job before worker cycle...")
        await run_token_refresh_job(db)

        if not are_workers_globally_enabled(db):
            logger.info("Global workers_enabled=false – skipping cycle for all accounts")
            return

        # Fetch all active ebay accounts.
        accounts: List[EbayAccount] = (
            db.query(EbayAccount)
            .filter(EbayAccount.is_active == True)  # noqa: E712
            .all()
        )
        if not accounts:
            logger.info("No active eBay accounts found – skipping worker cycle")
            return
        
        # Shuffle accounts to ensure fairness over time
        random.shuffle(accounts)

    finally:
        db.close()

    # Concurrency limit for accounts (e.g. 5 accounts at once)
    # Each account runs its own internal workers in parallel too.
    MAX_CONCURRENT_ACCOUNTS = 5
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ACCOUNTS)

    async def _run_safe(account_id: str, user_id: str, house_name: str):
        async with semaphore:
            try:
                logger.info(
                    "Running worker cycle for account id=%s ebay_user_id=%s house_name=%s",
                    account_id,
                    user_id,
                    house_name,
                )
                await run_cycle_for_account(account_id)
            except Exception as exc:
                logger.error(
                    "Worker cycle failed for account id=%s: %s",
                    account_id,
                    exc,
                    exc_info=True,
                )

    tasks = [
        _run_safe(
            acc.id,
            getattr(acc, "ebay_user_id", "unknown"),
            getattr(acc, "house_name", None)
        )
        for acc in accounts
    ]

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
