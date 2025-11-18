"""Tasks & Reminders background worker.

Periodically scans for due reminders (and snoozed reminders that woke up),
marks them as fired, and creates TaskNotification + system comments.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
import uuid

from sqlalchemy import or_, and_

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import Task, TaskComment, TaskNotification
from app.utils.logger import logger


async def process_due_reminders_once() -> Dict[str, Any]:
    """Process all reminders that should fire now.

    - type = 'reminder'
    - status = 'scheduled' and due_at <= now
      OR status = 'snoozed' and snooze_until <= now
    - deleted_at IS NULL
    """
    logger.info("Tasks reminder worker: scanning for due reminders...")

    db = SessionLocal()
    processed = 0
    now = datetime.now(timezone.utc)

    try:
        reminders = (
            db.query(Task)
            .filter(
                Task.type == "reminder",
                Task.deleted_at.is_(None),
                or_(
                    and_(Task.status == "scheduled", Task.due_at != None, Task.due_at <= now),  # noqa: E711
                    and_(Task.status == "snoozed", Task.snooze_until != None, Task.snooze_until <= now),  # noqa: E711
                ),
            )
            .all()
        )

        if not reminders:
            logger.info("Tasks reminder worker: no reminders to fire.")
            return {"status": "ok", "processed": 0, "timestamp": now.isoformat()}

        logger.info("Tasks reminder worker: found %d reminders to fire", len(reminders))

        for task in reminders:
            task.status = "fired"
            task.snooze_until = None

            fired_comment = TaskComment(
                id=str(uuid.uuid4()),
                task_id=task.id,
                author_id=None,
                body=f"Reminder fired at {now.isoformat()}",
                kind="system",
            )
            db.add(fired_comment)

            # Notify assignee, falling back to creator
            recipient_id = task.assignee_id or task.creator_id
            if recipient_id:
                notification = TaskNotification(
                    id=str(uuid.uuid4()),
                    task_id=task.id,
                    user_id=recipient_id,
                    kind="reminder_fired",
                    status="unread",
                )
                db.add(notification)

            processed += 1

        db.commit()
        logger.info("Tasks reminder worker: fired %d reminders", processed)

        return {"status": "ok", "processed": processed, "timestamp": now.isoformat()}

    except Exception as exc:  # pragma: no cover - safety net
        logger.error("Tasks reminder worker failed: %s", exc, exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(exc), "processed": processed, "timestamp": now.isoformat()}

    finally:
        db.close()


async def run_tasks_reminder_worker_loop(interval_seconds: int = 60) -> None:
    """Run the reminder firing worker in a simple interval loop.

    Default interval is 60 seconds.
    """
    logger.info("Tasks reminder worker loop started (interval=%s seconds)", interval_seconds)

    while True:
        try:
            result = await process_due_reminders_once()
            logger.info("Tasks reminder worker cycle completed: %s", result)
        except Exception as exc:  # pragma: no cover - safety net
            logger.error("Tasks reminder worker loop error: %s", exc, exc_info=True)

        await asyncio.sleep(interval_seconds)
