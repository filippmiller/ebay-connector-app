"""eBay data workers background loop.

Runs the generic ebay_workers scheduler every 5 minutes to trigger all
per-account workers (orders, transactions, offers, messages, cases,
finances, active inventory).
"""

import asyncio

from app.services.ebay_workers import run_cycle_for_all_accounts
from app.utils.logger import logger


async def run_ebay_workers_once() -> None:
    """Run one full workers cycle for all active accounts."""
    try:
        await run_cycle_for_all_accounts()
    except Exception as exc:
        logger.error("eBay workers cycle failed: %s", exc, exc_info=True)


async def run_ebay_workers_loop(interval_seconds: int = 300) -> None:
    """Run eBay workers in a loop.

    Default interval is 300 seconds (5 minutes).
    """
    logger.info("eBay workers loop started (interval=%s seconds)", interval_seconds)

    while True:
        await run_ebay_workers_once()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_ebay_workers_loop())
