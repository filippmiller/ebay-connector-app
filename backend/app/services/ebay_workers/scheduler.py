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


API_FAMILIES = ["orders"]  # later: "finances", "messages", "seller_transactions", ...


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
        state: EbaySyncState | None = (
            db.query(EbaySyncState)
            .filter(
                EbaySyncState.ebay_account_id == ebay_account_id,
                EbaySyncState.api_family == "orders",
            )
            .first()
        )
        if state and state.enabled:
            await run_orders_worker_for_account(ebay_account_id)

    finally:
        db.close()


async def run_cycle_for_all_accounts() -> None:
    """Run one sync cycle for all accounts that have any workers configured.

    This is intended to be triggered by an external scheduler (Railway cron,
    Cloudflare, etc.) approximately every 5 minutes.
    """

    db = _get_db()
    try:
        if not are_workers_globally_enabled(db):
            logger.info("Global workers_enabled=false – skipping cycle for all accounts")
            return

        accounts: List[EbayAccount] = ebay_account_service.get_accounts_by_org(db, org_id="*", active_only=True)  # placeholder
        # NOTE: ebay_account_service currently expects org_id; for now we can
        # simply fetch all accounts directly until we add a dedicated query.
        if not accounts:
            return
    finally:
        db.close()

    # In this initial implementation we will not fan out; the router will call
    # run_cycle_for_account for specific accounts. A full "all accounts" cycle
    # can be wired later once we add an efficient query for all active accounts.
    logger.info("run_cycle_for_all_accounts is currently a placeholder – call run_cycle_for_account per account")
