"""Inventory materialized view refresh worker.

This worker periodically refreshes the materialized views used for the
Inventory V3 grid SKU/ItemID Active/Sold counters:

- public.mv_tbl_parts_inventory_sku_counts
- public.mv_tbl_parts_inventory_itemid_counts

Schedule (Moscow time, UTC+3):
- From 00:00 to 08:00: refresh once per hour.
- From 08:00 to 24:00: refresh every 10 minutes.

The worker runs in an infinite loop and should be launched as a dedicated
Railway/Procfile worker, e.g.:

    python -m app.workers.inventory_mv_refresh_worker
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy.sql import text

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.ebay_workers import BackgroundWorker
from app.utils.logger import logger


# Stable key used in background_workers.worker_name and admin APIs
WORKER_NAME = "inventory_mv_refresh"

# Default interval (in seconds) used when the DB row has no explicit value.
DEFAULT_INTERVAL_SECONDS = 10 * 60  # 10 minutes


REFRESH_SQL = [
    "REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_tbl_parts_inventory_sku_counts",
    "REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_tbl_parts_inventory_itemid_counts",
]


def _run_refresh_cycle() -> None:
    """Run a single refresh cycle for both materialized views.

    Uses the models_sqlalchemy SessionLocal so that we talk to the same
    Supabase/Postgres database as the Inventory V3 grid.
    """
    logger.info("[inventory-mv-refresh] Starting refresh cycle for inventory MVs")
    db = SessionLocal()
    try:
        for sql in REFRESH_SQL:
            logger.info("[inventory-mv-refresh] Executing: %s", sql)
            db.execute(text(sql))
        db.commit()
        logger.info("[inventory-mv-refresh] Refresh cycle completed successfully")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "[inventory-mv-refresh] Refresh cycle failed: %s", exc, exc_info=True
        )
        try:
            db.rollback()
        except Exception:
            # best-effort rollback
            pass
    finally:
        db.close()


def _get_or_create_worker_row() -> BackgroundWorker | None:
    """Fetch or create the BackgroundWorker row for this worker.

    This mirrors the pattern used by other workers so that the admin API and
    Workers page can surface heartbeat information and configuration.
    """

    db = SessionLocal()
    try:
        worker: BackgroundWorker | None = (
            db.query(BackgroundWorker)
            .filter(BackgroundWorker.worker_name == WORKER_NAME)
            .one_or_none()
        )
        if worker is None:
            worker = BackgroundWorker(
                worker_name=WORKER_NAME,
                display_name="Inventory MV Refresh",
                description=(
                    "Refreshes inventory materialized views used by the Inventory V3 "
                    "grid (SKU/ItemID Active/Sold counters)."
                ),
                interval_seconds=DEFAULT_INTERVAL_SECONDS,
                enabled=True,
            )
            db.add(worker)
            db.commit()
            db.refresh(worker)
        return worker
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "[inventory-mv-refresh] Failed to load/create BackgroundWorker row: %s",
            exc,
        )
        return None
    finally:
        db.close()


def run_inventory_mv_refresh_once() -> tuple[bool, str | None]:
    """Execute a single refresh cycle and update BackgroundWorker status.

    This helper is used both by the long-running loop and by the admin
    "run once" endpoint. It always attempts a refresh regardless of the
    ``enabled`` flag; the periodic loop is responsible for honoring that
    toggle when deciding whether to call this function.
    """

    worker = _get_or_create_worker_row()
    status_error: str | None = None
    ok = False

    # Best-effort: update last_started_at / last_status before running.
    db = SessionLocal()
    try:
        if worker is not None:
            worker = db.merge(worker)
            now = datetime.now(timezone.utc)
            worker.last_started_at = now
            worker.last_status = "running"
            worker.last_error_message = None
            db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "[inventory-mv-refresh] Failed to update worker start heartbeat: %s",
            exc,
            exc_info=True,
        )

    try:
        _run_refresh_cycle()
        ok = True
    except Exception as exc:  # pragma: no cover - already logged in helper
        status_error = str(exc)
        ok = False

    # Update completion status.
    db2 = SessionLocal()
    try:
        if worker is not None:
            worker = db2.merge(worker)
            finished = datetime.now(timezone.utc)
            worker.last_finished_at = finished
            worker.last_status = "success" if ok else "error"
            worker.last_error_message = status_error[:2000] if status_error else None
            if ok:
                worker.runs_ok_in_row = (worker.runs_ok_in_row or 0) + 1
                worker.runs_error_in_row = 0
            else:
                worker.runs_error_in_row = (worker.runs_error_in_row or 0) + 1
            db2.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "[inventory-mv-refresh] Failed to update worker completion heartbeat: %s",
            exc,
            exc_info=True,
        )
    finally:
        db2.close()

    return ok, status_error


async def run_inventory_mv_refresh_loop() -> None:
    """Main loop for the inventory MV refresh worker.

    On each iteration the loop reads configuration from the
    ``background_workers`` table (worker_name = 'inventory_mv_refresh') and
    uses ``enabled`` + ``interval_seconds`` to decide whether to run and how
    long to sleep before the next cycle.
    """
    logger.info("[inventory-mv-refresh] Worker loop started")
    while True:
        # Load effective configuration for this iteration.
        db = SessionLocal()
        try:
            worker: BackgroundWorker | None = (
                db.query(BackgroundWorker)
                .filter(BackgroundWorker.worker_name == WORKER_NAME)
                .one_or_none()
            )
            if worker is None:
                # Ensure a row exists so the admin UI has something to edit.
                worker = BackgroundWorker(
                    worker_name=WORKER_NAME,
                    display_name="Inventory MV Refresh",
                    description=(
                        "Refreshes inventory materialized views used by the Inventory V3 "
                        "grid (SKU/ItemID Active/Sold counters)."
                    ),
                    interval_seconds=DEFAULT_INTERVAL_SECONDS,
                    enabled=True,
                )
                db.add(worker)
                db.commit()
                db.refresh(worker)

            enabled = bool(worker.enabled)
            interval = worker.interval_seconds or DEFAULT_INTERVAL_SECONDS
            if interval <= 0:
                interval = DEFAULT_INTERVAL_SECONDS
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[inventory-mv-refresh] Failed to load worker settings: %s", exc, exc_info=True
            )
            enabled = True
            interval = DEFAULT_INTERVAL_SECONDS
        finally:
            db.close()

        if not enabled:
            logger.info(
                "[inventory-mv-refresh] Worker disabled in DB; sleeping %s seconds without running",
                interval,
            )
            await asyncio.sleep(interval)
            continue

        try:
            ok, err = run_inventory_mv_refresh_once()
            if ok:
                logger.info("[inventory-mv-refresh] Cycle completed successfully")
            else:
                logger.error(
                    "[inventory-mv-refresh] Cycle completed with error: %s", err or "unknown_error"
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[inventory-mv-refresh] Unexpected error in loop: %s", exc, exc_info=True
            )

        logger.info(
            "[inventory-mv-refresh] Next refresh in %s seconds (from DB config)", interval
        )
        await asyncio.sleep(interval)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_inventory_mv_refresh_loop())
