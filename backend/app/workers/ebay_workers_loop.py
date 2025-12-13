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
from app.utils.build_info import get_build_number
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
    """Run one full workers cycle for all active accounts.
    
    Uses the same code path as the manual "Run Now" button to ensure
    consistent behavior.
    
    NOTE: When running as a separate Railway worker service, use
    run_ebay_workers_proxy_loop() or run_transactions_worker_proxy_loop()
    instead, which delegate to the Web App's internal endpoints to ensure
    consistent token handling and avoid decryption issues.
    """
    from app.services.ebay_workers.orders_worker import run_orders_worker_for_account
    from app.services.ebay_workers.transactions_worker import run_transactions_worker_for_account
    from app.services.ebay_workers.offers_worker import run_offers_worker_for_account
    from app.services.ebay_workers.messages_worker import run_messages_worker_for_account
    from app.services.ebay_workers.active_inventory_worker import run_active_inventory_worker_for_account
    from app.services.ebay_workers.cases_worker import run_cases_worker_for_account
    from app.services.ebay_workers.finances_worker import run_finances_worker_for_account
    from app.services.ebay_workers.purchases_worker import run_purchases_worker_for_account
    from app.services.ebay_workers.inquiries_worker import run_inquiries_worker_for_account
    from app.services.ebay_workers.returns_worker import run_returns_worker_for_account
    from app.services.ebay_workers.state import are_workers_globally_enabled
    from app.models_sqlalchemy.ebay_workers import EbaySyncState
    from app.models_sqlalchemy.models import EbayAccount
    from app.services.ebay_token_refresh_service import run_token_refresh_job
    
    db = SessionLocal()
    try:
        logger.info("Running workers cycle (manual code path)...")
        
        # 1. Refresh tokens first
        await run_token_refresh_job(db, triggered_by="loop_scheduler")
        
        # 2. Check if workers are globally enabled
        if not are_workers_globally_enabled(db):
            logger.info("Workers globally disabled - skipping cycle")
            return
        
        # 3. Get all active accounts
        accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
        if not accounts:
            logger.info("No active accounts found - skipping cycle")
            return
        
        logger.info(f"Running workers for {len(accounts)} accounts...")
        
        # 4. Run workers for each account using the SAME pattern as manual "Run Now"
        for account in accounts:
            account_id = account.id
            
            # Map of API families to worker functions
            worker_map = {
                "orders": run_orders_worker_for_account,
                "transactions": run_transactions_worker_for_account,
                "offers": run_offers_worker_for_account,
                "messages": run_messages_worker_for_account,
                "active_inventory": run_active_inventory_worker_for_account,
                "buyer": run_purchases_worker_for_account,
                "cases": run_cases_worker_for_account,
                "inquiries": run_inquiries_worker_for_account,
                "finances": run_finances_worker_for_account,
                "returns": run_returns_worker_for_account,
            }
            
            for api_family, worker_func in worker_map.items():
                # Check if this worker is enabled for this account
                state = db.query(EbaySyncState).filter(
                    EbaySyncState.ebay_account_id == account_id,
                    EbaySyncState.api_family == api_family,
                ).first()
                
                if not state or not state.enabled:
                    continue
                
                try:
                    # Call worker with triggered_by="manual" to use the exact same code path
                    # that works when users click "Run Now"
                    run_id = await worker_func(account_id, triggered_by="manual")
                    if run_id:
                        logger.info(f"Worker {api_family} started for {account.house_name}: run_id={run_id}")
                except Exception as e:
                    logger.error(f"Worker {api_family} failed for account {account_id}: {e}", exc_info=True)
        
        logger.info("Workers cycle completed")
        
    except Exception as exc:
        logger.error("eBay workers cycle failed: %s", exc, exc_info=True)
    finally:
        db.close()


async def run_ebay_workers_loop(interval_seconds: int = 300) -> None:
    """Run eBay workers in a loop.

    Default interval is 300 seconds (5 minutes).
    """
    build_number = get_build_number()
    logger.info("=" * 60)
    logger.info("eBay workers loop started (interval=%s seconds) BUILD=%s", interval_seconds, build_number)
    logger.info("=" * 60)

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


async def run_transactions_worker_proxy_once() -> dict:
    """Run ONLY the Transactions worker via the internal API endpoint.
    
    This ensures transactions sync uses the exact same code path as manual "Run Now"
    by delegating to the Web App's internal endpoint.
    
    Returns:
        Dict with result from the internal API
    """
    import httpx
    import os
    
    web_app_url = os.getenv("WEB_APP_URL", "").rstrip("/")
    internal_api_key = os.getenv("INTERNAL_API_KEY", "")
    
    if not web_app_url:
        error = "WEB_APP_URL not configured"
        logger.error(f"[transactions_proxy] {error}")
        return {"status": "error", "error": error}
    
    if not internal_api_key:
        error = "INTERNAL_API_KEY not configured"
        logger.error(f"[transactions_proxy] {error}")
        return {"status": "error", "error": error}
    
    endpoint = f"{web_app_url}/api/admin/internal/workers/transactions/run-once"
    
    try:
        logger.info(f"[transactions_proxy] Triggering transactions sync via {endpoint}...")
        
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                endpoint,
                json={"internal_api_key": internal_api_key},
            )
            
            if resp.status_code == 200:
                result = resp.json()
                logger.info(
                    "[transactions_proxy] SUCCESS: status=%s processed=%s succeeded=%s failed=%s",
                    result.get("status"),
                    result.get("accounts_processed", 0),
                    result.get("accounts_succeeded", 0),
                    result.get("accounts_failed", 0),
                )
                return result
            else:
                error_text = resp.text[:500]
                logger.error(
                    "[transactions_proxy] FAILED: HTTP %d - %s",
                    resp.status_code, error_text,
                )
                return {
                    "status": "error",
                    "http_status": resp.status_code,
                    "error": error_text,
                }
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[transactions_proxy] Exception: {error_msg}", exc_info=True)
        return {"status": "error", "error": error_msg}


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
                    result = resp.json()
                    logger.info(
                        "Proxy trigger completed: status=%s accounts=%s",
                        result.get("status"),
                        result.get("accounts_processed", 0),
                    )
                else:
                    logger.error(f"Proxy trigger failed: HTTP {resp.status_code} {resp.text}")
                    
        except Exception as e:
            logger.error(f"Proxy trigger failed: {e}")
        
        await asyncio.sleep(interval_seconds)


async def run_transactions_worker_proxy_loop(interval_seconds: int = 300) -> None:
    """Run ONLY the Transactions worker in Proxy Mode on a schedule.
    
    This is a dedicated loop for running only the Transactions worker,
    useful for isolating transaction syncs from other workers.
    """
    build_number = get_build_number()
    logger.info("=" * 60)
    logger.info(
        "[transactions_proxy_loop] Started (interval=%d seconds) BUILD=%s",
        interval_seconds, build_number
    )
    logger.info("=" * 60)
    
    while True:
        result = await run_transactions_worker_proxy_once()
        
        if result.get("status") == "error":
            logger.warning(
                "[transactions_proxy_loop] Cycle had error: %s",
                result.get("error", "unknown"),
            )
        
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    import sys
    
    # When run as a script, support different modes via command line argument
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if mode == "transactions":
        # Run ONLY transactions worker via proxy
        logger.info("Starting Transactions-only worker proxy loop...")
        asyncio.run(run_transactions_worker_proxy_loop())
    else:
        # Run ALL workers via proxy (default behavior)
        logger.info("Starting ALL workers proxy loop...")
        asyncio.run(run_ebay_workers_proxy_loop())
