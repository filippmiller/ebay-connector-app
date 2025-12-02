"""eBay data workers background loop.

Runs the generic ebay_workers scheduler every 5 minutes to trigger all
per-account workers (orders, transactions, offers, messages, cases,
finances, active inventory).

This module is used in two ways:
- As a library function, via :func:`run_ebay_workers_loop`, which the main
  FastAPI app starts on startup (see app.main.startup_event).
- Historically, as a standalone entrypoint via ``python -m
  app.workers.ebay_workers_loop``. In practice, the main API-hosted loop is
  the authoritative one in production.

A small heartbeat is recorded in the BackgroundWorker table with
worker_name="ebay_workers_loop" so the admin API/UI can show when the loop
last ran and whether it appears stale.
"""

import asyncio
from datetime import datetime, timezone

from app.services.ebay_workers import run_cycle_for_all_accounts
from app.utils.logger import logger
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.ebay_workers import BackgroundWorker


WORKER_NAME = "ebay_workers_loop"


def _get_or_create_worker_row(db: SessionLocal) -> BackgroundWorker | None:
    """Fetch or create the BackgroundWorker row for the eBay workers loop.

    This mirrors the pattern used by the token refresh worker so that the
    admin API can surface heartbeat information (last_started_at,
    last_finished_at, last_status, runs_ok_in_row, runs_error_in_row).
    """

    try:
        worker: BackgroundWorker | None = (
            db.query(BackgroundWorker)
            .filter(BackgroundWorker.worker_name == WORKER_NAME)
            .one_or_none()
        )
        if worker is None:
            worker = BackgroundWorker(
                worker_name=WORKER_NAME,
                interval_seconds=None,  # filled from the actual loop interval below
            )
            db.add(worker)
            db.commit()
            db.refresh(worker)
        return worker
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to load/create BackgroundWorker row for ebay_workers_loop: %s", exc)
        return None


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

    db = SessionLocal()
    worker_row = _get_or_create_worker_row(db)
    if worker_row is not None:
        # Persist the effective interval used by this loop so status endpoints
        # do not have to guess.
        worker_row.interval_seconds = interval_seconds
        db.commit()

    try:
        while True:
            started = datetime.now(timezone.utc)
            if worker_row is not None:
                worker_row.last_started_at = started
                worker_row.last_status = "running"
                worker_row.last_error_message = None
                db.commit()

            # Run a single full cycle; individual worker errors are handled
            # inside run_cycle_for_all_accounts, so reaching this point is
            # considered a "successful" loop iteration.
            await run_ebay_workers_once()

            finished = datetime.now(timezone.utc)
            if worker_row is not None:
                worker_row.last_finished_at = finished
                worker_row.last_status = "ok"
                worker_row.runs_ok_in_row = (worker_row.runs_ok_in_row or 0) + 1
                worker_row.runs_error_in_row = 0
                db.commit()

            await asyncio.sleep(interval_seconds)
    except Exception as exc:  # pragma: no cover - defensive
        # If the outer loop itself fails, record the error so the admin UI can
        # surface it. The process will typically be restarted by the platform.
        logger.error("eBay workers loop failed: %s", exc, exc_info=True)
        if worker_row is not None:
            worker_row.last_status = "error"
            worker_row.last_error_message = str(exc)[:2000]
            worker_row.last_finished_at = datetime.now(timezone.utc)
            worker_row.runs_error_in_row = (worker_row.runs_error_in_row or 0) + 1
            db.commit()
        raise
    finally:
        try:
            db.close()
        except Exception:  # pragma: no cover - defensive
            pass


async def run_ebay_workers_proxy_loop(interval_seconds: int = 300) -> None:
    """Run the eBay workers loop in Proxy Mode.
    
    Delegates execution to the Web App via internal API.
    This is used when running as a standalone service to avoid environment/decryption issues.
    """
    import httpx
    import os
    
    logger.info("eBay workers loop started (API Proxy Mode)")
    
    web_app_url = os.getenv("WEB_APP_URL", "").rstrip("/")
    internal_api_key = os.getenv("INTERNAL_API_KEY", "")
    
    if not web_app_url:
        logger.error("Proxy mode requires WEB_APP_URL")
        return
    if not internal_api_key:
        logger.error("Proxy mode requires INTERNAL_API_KEY")
        return

    while True:
        try:
            endpoint = f"{web_app_url}/api/admin/internal/run-ebay-workers"
            logger.info(f"Triggering worker cycle via {endpoint}...")
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    endpoint,
                    json={"internal_api_key": internal_api_key},
                )
                if resp.status_code == 200:
                    logger.info("Proxy trigger sent successfully")
                else:
                    logger.error(f"Proxy trigger failed: HTTP {resp.status_code} {resp.text}")
                    
        except Exception as e:
            logger.error(f"Proxy trigger failed: {e}")
        
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    # When run as a script, default to Proxy Mode to ensure we use the Web App's
    # environment and keys for decryption.
    asyncio.run(run_ebay_workers_proxy_loop())
