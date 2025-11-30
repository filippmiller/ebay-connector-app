"""Gmail sync worker.

Fetches messages for all active Gmail integration accounts and builds
AiEmailTrainingPair rows for training the email assistant.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import IntegrationAccount, IntegrationProvider
from app.services.gmail_sync import sync_gmail_account
from app.utils.logger import logger


async def run_gmail_sync_once(max_accounts: int = 50) -> Dict[str, Any]:
    """Run one sync cycle for all active Gmail integration accounts.

    This helper is safe to call from tests or ad-hoc scripts. It returns a
    summary with per-account results suitable for logging or diagnostics.
    """

    db: Session = SessionLocal()
    results: List[Dict[str, Any]] = []

    try:
        provider = (
            db.query(IntegrationProvider)
            .filter(IntegrationProvider.code == "gmail")
            .one_or_none()
        )
        if not provider:
            logger.info("[gmail-sync] No Gmail provider configured; skipping cycle")
            return {"status": "ok", "accounts_processed": 0, "results": []}

        accounts: List[IntegrationAccount] = (
            db.query(IntegrationAccount)
            .filter(
                IntegrationAccount.provider_id == provider.id,
                IntegrationAccount.status == "active",
            )
            .order_by(IntegrationAccount.last_sync_at.is_(True), IntegrationAccount.last_sync_at.asc())
            .limit(max_accounts)
            .all()
        )

        if not accounts:
            logger.info("[gmail-sync] No active Gmail accounts to process")
            return {"status": "ok", "accounts_processed": 0, "results": []}

        logger.info("[gmail-sync] Starting sync for %d Gmail accounts", len(accounts))

        for account in accounts:
            try:
                summary = await sync_gmail_account(db, account.id, manual=False)
                results.append(summary)
                logger.info(
                    "[gmail-sync] account_id=%s messages=%s pairs_created=%s errors=%s",
                    account.id,
                    summary.get("messages_upserted"),
                    summary.get("pairs_created"),
                    len(summary.get("errors") or []),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "[gmail-sync] account_id=%s failed: %s",
                    account.id,
                    exc,
                    exc_info=True,
                )
                results.append(
                    {
                        "account_id": account.id,
                        "messages_fetched": 0,
                        "messages_upserted": 0,
                        "pairs_created": 0,
                        "pairs_skipped_existing": 0,
                        "errors": [f"sync_exception:{type(exc).__name__}"],
                    }
                )

        return {
            "status": "ok",
            "accounts_processed": len(accounts),
            "results": results,
        }

    finally:
        db.close()


async def run_gmail_sync_loop(interval_seconds: int = 300) -> None:
    """Run the Gmail sync worker in an infinite loop.

    Default interval is 300 seconds (5 minutes).
    """

    logger.info(
        "[gmail-sync] Gmail sync worker loop started (interval=%s seconds)",
        interval_seconds,
    )

    while True:
        try:
            summary = await run_gmail_sync_once()
            logger.info("[gmail-sync] cycle completed: %s", summary)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[gmail-sync] loop error: %s", exc, exc_info=True)

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    asyncio.run(run_gmail_sync_loop())