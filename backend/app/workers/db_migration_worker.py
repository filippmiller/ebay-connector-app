"""DB migration workers background loop.

Runs incremental MSSQL→Supabase workers configured in db_migration_workers.

Each cycle:
- Loads all enabled workers.
- For each worker whose interval has elapsed, runs a single incremental sync
  using the same helper as the admin API.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text

from app.models_sqlalchemy import engine as pg_engine, SessionLocal
from app.models_sqlalchemy.models import Task, TaskNotification
from app.utils.logger import logger
from app.routers import admin_db_migration_console as migration_console


def _create_worker_notification(
    *,
    user_id: str,
    title: str,
    description: str,
    kind: str,
) -> None:
    """Create a Task+TaskNotification popup for a migration worker event.

    This uses type='reminder' and status='fired' so it behaves like a
    one-off reminder that has already fired.
    """

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        task = Task(
            id=str(uuid.uuid4()),
            type="reminder",
            title=title,
            description=description,
            creator_id=user_id,
            assignee_id=user_id,
            status="fired",
            priority="normal",
            due_at=now,
            is_popup=True,
        )
        db.add(task)
        db.flush()

        notif = TaskNotification(
            task_id=task.id,
            user_id=user_id,
            kind=kind,
            status="unread",
        )
        db.add(notif)
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("[db-migration-worker] Failed to create notification: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()


async def run_db_migration_workers_once(max_workers: int = 20) -> Dict[str, Any]:
    """Run one incremental cycle for all enabled db_migration_workers.

    This is best-effort and logs failures per worker. It is safe to call from
    tests or ad-hoc scripts.
    """

    now = datetime.now(timezone.utc)
    summaries: List[Dict[str, Any]] = []

    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  id,
                  source_database,
                  source_schema,
                  source_table,
                  target_schema,
                  target_table,
                  pk_column,
                  worker_enabled,
                  interval_seconds,
                  owner_user_id,
                  notify_on_success,
                  notify_on_error,
                  last_run_started_at
                FROM db_migration_workers
                WHERE worker_enabled = TRUE
                ORDER BY id
                LIMIT :limit
                """
            ),
            {"limit": max_workers},
        ).mappings().all()

    if not rows:
        logger.info("[db-migration-worker] No enabled workers found; skipping cycle")
        return {"status": "ok", "workers_processed": 0, "summaries": []}

    for row in rows:
        wid = row["id"]
        last_started = row["last_run_started_at"]
        interval = int(row["interval_seconds"] or 300)

        if last_started is not None:
            # last_started is a datetime from SQLAlchemy mapping.
            elapsed = (now - last_started).total_seconds()
            if elapsed < interval:
                continue

        owner_user_id = row.get("owner_user_id")
        notify_on_success = bool(row.get("notify_on_success"))
        notify_on_error = bool(row.get("notify_on_error"))

        try:
            logger.info(
                "[db-migration-worker] Running worker id=%s for %s.%s → %s.%s",
                wid,
                row["source_schema"],
                row["source_table"],
                row["target_schema"],
                row["target_table"],
            )
            # Single best-effort incremental pass for this worker. The helper
            # is idempotent thanks to ON CONFLICT(pk) DO NOTHING on the target
            # table, so reruns after crashes / timeouts are safe.
            summary = migration_console.run_worker_incremental_sync(
                source_database=row["source_database"],
                source_schema=row["source_schema"],
                source_table=row["source_table"],
                target_schema=row["target_schema"],
                target_table=row["target_table"],
                pk_column=row["pk_column"],
                batch_size=5000,
                worker_id=wid,
                max_seconds=None,  # background loop can run as long as needed
            )
            summaries.append({"worker_id": wid, **summary})

            if owner_user_id and notify_on_success:
                title = (
                    f"DB migration OK: {row['source_schema']}.{row['source_table']} → "
                    f"{row['target_schema']}.{row['target_table']}"
                )
                desc = (
                    f"Worker {wid} inserted {summary.get('rows_inserted', 0)} rows in "
                    f"{summary.get('batches', 0)} batches. "
                    f"Source rows: {summary.get('source_row_count')}, "
                    f"target rows: {summary.get('target_row_count')}."
                )
                _create_worker_notification(
                    user_id=owner_user_id,
                    title=title,
                    description=desc,
                    kind="migration_worker_success",
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[db-migration-worker] Worker id=%s failed: %s", wid, exc, exc_info=True
            )
            summaries.append(
                {
                    "worker_id": wid,
                    "status": "error",
                    "error": str(exc),
                }
            )
            if owner_user_id and notify_on_error:
                title = (
                    f"DB migration ERROR: {row['source_schema']}.{row['source_table']} → "
                    f"{row['target_schema']}.{row['target_table']}"
                )
                desc = f"Worker {wid} failed with error: {exc}"
                _create_worker_notification(
                    user_id=owner_user_id,
                    title=title,
                    description=desc,
                    kind="migration_worker_error",
                )

    return {"status": "ok", "workers_processed": len(summaries), "summaries": summaries}


async def run_db_migration_workers_loop(interval_seconds: int = 60) -> None:
    """Run db migration workers in an infinite loop.

    This loop periodically invokes :func:`run_db_migration_workers_once` and
    then sleeps for ``interval_seconds``. Each worker also has its own
    per-worker interval; this outer loop just provides a global heartbeat.
    """

    logger.info(
        "[db-migration-worker] Worker loop started (interval=%s seconds)",
        interval_seconds,
    )

    while True:
        try:
            summary = await run_db_migration_workers_once()
            logger.info("[db-migration-worker] cycle completed: %s", summary)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[db-migration-worker] loop error: %s", exc, exc_info=True
            )

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    asyncio.run(run_db_migration_workers_loop())