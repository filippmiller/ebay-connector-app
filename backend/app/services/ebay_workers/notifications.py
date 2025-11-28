from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
import uuid

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, Task, TaskNotification
from app.utils.logger import logger


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:  # noqa: BLE001
        return None


def create_worker_run_notification(
    db: Session,
    *,
    account: EbayAccount,
    api_family: str,
    run_status: str,
    summary: Optional[Mapping[str, Any]] = None,
) -> None:
    """Create a Task + TaskNotification for a completed/failed worker run.

    This helper is intentionally lightweight and best-effort: failures are
    logged but never allowed to break the worker execution path.
    """

    owner_id = account.org_id
    if not owner_id:
        # Without an owning org/user there is nobody to notify.
        return

    try:
        total_fetched = _safe_int((summary or {}).get("total_fetched"))
        total_stored = _safe_int((summary or {}).get("total_stored"))
        window_from = (summary or {}).get("window_from")
        window_to = (summary or {}).get("window_to")
        sync_run_id = (summary or {}).get("sync_run_id")
        error_message = (summary or {}).get("error_message") or (summary or {}).get("error")

        status_normalized = (run_status or "").lower()
        is_success = status_normalized in {"completed", "success", "ok"}

        worker_label = api_family.replace("_", " ")
        house = account.house_name or account.username or account.ebay_user_id or account.id

        title_suffix = "completed" if is_success else "failed"
        title = f"eBay {worker_label} worker for {house} {title_suffix}"

        lines = []
        if window_from or window_to:
            lines.append(f"Window: {window_from or 'unknown'} → {window_to or 'unknown'}")
        if total_fetched is not None or total_stored is not None:
            lines.append(f"Fetched: {total_fetched if total_fetched is not None else '–'}; "
                         f"Stored: {total_stored if total_stored is not None else '–'}")
        if sync_run_id:
            lines.append(f"Sync run id: {sync_run_id}")
        if not is_success and error_message:
            lines.append(f"Error: {error_message}")

        description = "\n".join(lines) if lines else None

        # For worker notifications we model them as fired reminders so they
        # appear in the notifications UI but are not actionable todo items.
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            type="reminder",
            title=title,
            description=description,
            creator_id=owner_id,
            assignee_id=owner_id,
            status="fired" if is_success else "done",
            priority="normal",
            is_popup=True,
            due_at=None,
        )
        db.add(task)

        notification = TaskNotification(
            id=str(uuid.uuid4()),
            task_id=task_id,
            user_id=owner_id,
            kind=f"ebay_worker_{api_family}_{'completed' if is_success else 'failed'}",
            status="unread",
        )
        db.add(notification)

        db.commit()

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to create worker notification for account=%s api=%s: %s",
            getattr(account, "id", None),
            api_family,
            exc,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            # Best-effort rollback; worker transaction may already be committed.
            pass
