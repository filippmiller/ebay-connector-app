"""Sniper executor worker (stub implementation).

Periodically scans ebay_snipes for pending snipes that should fire soon and
marks them as executed_stub with a placeholder result_message. This is a
minimal worker skeleton; it does NOT place real eBay bids yet.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbaySnipe
from app.utils.logger import logger


POLL_INTERVAL_SECONDS = 5
SAFETY_MARGIN_SECONDS = 2


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _pick_due_snipes(db: Session, now: datetime) -> List[EbaySnipe]:
    """Return pending snipes whose fire time has passed.

    Fire time is computed as end_time - (seconds_before_end + SAFETY_MARGIN).
    """

    q = db.query(EbaySnipe).filter(EbaySnipe.status == "pending")
    candidates: List[EbaySnipe] = q.all()
    due: List[EbaySnipe] = []

    for s in candidates:
        if not s.end_time:
            continue
        secs = s.seconds_before_end or 0
        fire_at = s.end_time - timedelta(seconds=secs + SAFETY_MARGIN_SECONDS)
        if now >= fire_at:
            due.append(s)

    return due


async def run_sniper_once() -> int:
    """Run a single sniper evaluation tick.

    Returns the number of snipes processed.
    """

    db: Session = SessionLocal()
    processed = 0
    now = _now_utc()
    try:
        snipes = _pick_due_snipes(db, now)
        if not snipes:
            return 0

        logger.info("Sniper executor: found %d due snipes", len(snipes))

        for s in snipes:
            try:
                s.status = "executed_stub"
                s.result_message = (
                    "SNIPER_STUB_EXECUTED — real eBay bid is not implemented yet"
                )
                s.updated_at = now
                processed += 1
            except Exception as exc:  # pragma: no cover - safety net
                logger.error(
                    "Sniper executor: failed to process snipe id=%s: %s", s.id, exc
                )

        db.commit()
        return processed
    finally:
        db.close()


async def run_sniper_loop(interval_seconds: int = POLL_INTERVAL_SECONDS) -> None:
    """Background loop for the sniper executor.

    Designed to be run as a standalone worker process (e.g. Railway service).
    """

    logger.info("Sniper executor loop started (interval=%s seconds)", interval_seconds)

    while True:
        try:
            count = await run_sniper_once()
            if count:
                logger.info("Sniper executor: processed %d snipes in this tick", count)
        except Exception as exc:  # pragma: no cover - safety net
            logger.error("Sniper executor loop error: %s", exc, exc_info=True)

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":  # pragma: no cover - manual run helper
    asyncio.run(run_sniper_loop())