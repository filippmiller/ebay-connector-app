"""Sniper executor worker (stub implementation).

Periodically scans ebay_snipes for pending snipes that should fire soon and
marks them as executed_stub with a placeholder result_message. This is a
minimal worker skeleton; it does NOT place real eBay bids yet.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbaySnipe, EbaySnipeStatus, EbaySnipeLog
from app.utils.logger import logger


# Poll interval is configurable via env; default to 1s for precise scheduling.
try:
    POLL_INTERVAL_SECONDS = max(1, int(os.getenv("SNIPER_POLL_INTERVAL_SECONDS", "1")))
except ValueError:
    POLL_INTERVAL_SECONDS = 1


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _pick_due_snipes(db: Session, now: datetime) -> List[EbaySnipe]:
    """Return snipes whose fire_at has passed but auction has not ended.

    This uses the explicit fire_at column computed at creation/update time
    instead of re-deriving the schedule expression on every tick.
    """

    q = (
        db.query(EbaySnipe)
        .filter(
            EbaySnipe.status == EbaySnipeStatus.scheduled.value,
            EbaySnipe.fire_at <= now,
            EbaySnipe.end_time > now,
        )
        .order_by(EbaySnipe.fire_at.asc())
    )

    return list(q.all())


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
                # Stub implementation: mark the snipe as executed_stub. In a
                # future iteration this is where we will call the real eBay
                # PlaceOffer/Browse API and move the snipe into a proper
                # BIDDING/WON/LOST lifecycle.
                s.status = EbaySnipeStatus.executed_stub.value
                s.result_message = (
                    "SNIPER_STUB_EXECUTED — real eBay bid is not implemented yet"
                )
                s.has_bid = True
                s.updated_at = now

                # Record a simple log entry so we already exercise the logging
                # pipeline in the stub implementation. Real bidding will enrich
                # this with the actual eBay response payload and IDs.
                log_entry = EbaySnipeLog(
                    snipe_id=s.id,
                    event_type="stub_execute",
                    status=EbaySnipeStatus.executed_stub.value,
                    http_status=None,
                    payload=None,
                    message="Stub sniper execution: no real eBay bid was sent",
                )
                db.add(log_entry)

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