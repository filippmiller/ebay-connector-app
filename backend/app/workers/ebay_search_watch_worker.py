"""eBay Search Watch worker.

Periodically executes user-defined ebay_search_watches rules against the eBay
Browse API and generates internal notifications for new matching listings.

First iteration focuses on a conservative implementation:
- Uses a shared application Browse token (read-only scope).
- Applies simple filters (price + shipping, category_hint, exclude_keywords).
- Deduplicates notifications per watch via last_seen_item_ids.
- Creates/updates a single Task per watch (if notification_mode == 'task') and
  appends system comments for each new listing.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbaySearchWatch, Task, TaskComment, TaskNotification
from app.services.ebay import ebay_service
from app.services.ebay_api_client import search_active_listings
from app.utils.logger import logger


async def run_search_watch_loop(interval_sec: int = 60) -> None:
    """Background loop that periodically processes all active search watches.

    The loop itself is lightweight; per-watch throttling is controlled via
    EbaySearchWatch.check_interval_sec and last_checked_at.
    """

    logger.info("[watch] eBay search watch loop started (interval=%s seconds)", interval_sec)
    while True:
        try:
            await process_search_watches_once()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[watch] process_search_watches_once failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval_sec)


async def process_search_watches_once(max_watches: int = 200) -> Dict[str, Any]:
    """Process a batch of ebay_search_watches.

    Returns a small summary dict for logging/diagnostics.
    """

    db = SessionLocal()
    now = datetime.now(timezone.utc)

    processed = 0
    matches_total = 0

    try:
        watches: List[EbaySearchWatch] = (
            db.query(EbaySearchWatch)
            .filter(EbaySearchWatch.enabled.is_(True))
            .order_by(EbaySearchWatch.created_at.asc())
            .limit(max_watches)
            .all()
        )

        if not watches:
            return {"status": "ok", "processed": 0, "matches": 0, "timestamp": now.isoformat()}

        # Shared Browse app-token for this cycle.
        try:
            access_token = await ebay_service.get_browse_app_token()
        except Exception as exc:
            logger.error("[watch] Failed to obtain Browse app-token: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc), "processed": 0, "matches": 0, "timestamp": now.isoformat()}

        for watch in watches:
            # Per-watch throttling based on check_interval_sec
            if watch.check_interval_sec and watch.last_checked_at is not None:
                delta = (now - watch.last_checked_at).total_seconds()
                if delta < max(10, watch.check_interval_sec):
                    continue

            try:
                added = await _process_single_watch(db, watch, access_token, now)
                matches_total += added
                processed += 1
            except Exception as exc:  # pragma: no cover - per-watch isolation
                logger.error(
                    "[watch] Failed to process ebay_search_watch id=%s: %s", watch.id, exc, exc_info=True
                )

        db.commit()

        return {
            "status": "ok",
            "processed": processed,
            "matches": matches_total,
            "timestamp": now.isoformat(),
        }

    finally:
        db.close()


async def _process_single_watch(db: Session, watch: EbaySearchWatch, access_token: str, now: datetime) -> int:
    """Run Browse search for a single watch and persist any new matches.

    Returns the number of *new* listings that resulted in notifications.
    """

    keywords = (watch.keywords or "").strip()
    if not keywords:
        # Nothing to search for – mark as checked and skip.
        watch.last_checked_at = now
        return 0

    listings = await search_active_listings(access_token, keywords, limit=50)

    # Prepare filters from the watch row.
    max_total = float(watch.max_total_price or 0) if watch.max_total_price is not None else None
    category_hint = (watch.category_hint or "").strip() or None
    exclude = [
        (w or "").strip().lower()
        for w in (watch.exclude_keywords or [])
        if (w or "").strip()
    ]

    seen_ids: List[str] = list(watch.last_seen_item_ids or [])
    seen_set = {str(i) for i in seen_ids}

    def _accept(summary) -> bool:
        total_price = float((summary.price or 0.0) + (summary.shipping or 0.0))
        if max_total is not None and total_price > max_total:
            return False

        title = (summary.title or "").lower()
        desc = (summary.description or "").lower()

        if category_hint and category_hint.lower() == "laptop":
            laptop_tokens = ["laptop", "notebook", "ноутбук"]
            if not (any(t in title for t in laptop_tokens) or any(t in desc for t in laptop_tokens)):
                return False

        for bad in exclude:
            if bad in title or bad in desc:
                return False

        return True

    new_matches = 0

    for s in listings:
        item_id = str(s.item_id)
        if item_id in seen_set:
            continue
        if not _accept(s):
            continue

        # Mark as seen regardless of notification outcome so we do not spam.
        seen_set.add(item_id)
        seen_ids.append(item_id)

        try:
            if watch.notification_mode == "task":
                _create_task_notification_for_match(db, watch, s, now)
            # Future modes (email, webhook, etc.) can be added here.
            new_matches += 1
        except Exception as exc:  # pragma: no cover - best-effort per match
            logger.error(
                "[watch] Failed to create notification for watch_id=%s item_id=%s: %s",
                watch.id,
                item_id,
                exc,
                exc_info=True,
            )

    # Keep a bounded number of last seen IDs to avoid unbounded JSON growth.
    MAX_SEEN = 200
    if len(seen_ids) > MAX_SEEN:
        seen_ids = seen_ids[-MAX_SEEN:]

    watch.last_seen_item_ids = seen_ids
    watch.last_checked_at = now

    return new_matches


def _get_or_create_watch_task(db: Session, watch: EbaySearchWatch) -> Task:
    """Return a Task representing this watch, creating it if necessary.

    One Task per watch keeps the UI concise: new listings become comments.
    """

    task: Optional[Task] = (
        db.query(Task)
        .filter(
            Task.type == "reminder",
            Task.creator_id == watch.user_id,
            Task.title == f"eBay авто-поиск: {watch.name}",
        )
        .one_or_none()
    )

    if task is not None:
        return task

    now = datetime.now(timezone.utc)
    task = Task(
        id=str(uuid.uuid4()),
        type="reminder",
        title=f"eBay авто-поиск: {watch.name}",
        description=(
            "Авто-поиск по eBay. Новые подходящие лоты будут появляться в виде "
            "комментариев к этой задаче."
        ),
        creator_id=watch.user_id,
        assignee_id=watch.user_id,
        status="scheduled",
        priority="normal",
        due_at=None,
        is_popup=True,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.flush()  # ensure task.id is available

    return task


def _create_task_notification_for_match(
    db: Session,
    watch: EbaySearchWatch,
    summary,
    now: datetime,
) -> None:
    """Append a comment about a new listing and create TaskNotification."""

    task = _get_or_create_watch_task(db, watch)

    total_price = float((summary.price or 0.0) + (summary.shipping or 0.0))
    price_str = f"{float(summary.price or 0.0):.2f}"
    ship_str = f"{float(summary.shipping or 0.0):.2f}"
    total_str = f"{total_price:.2f}"

    ebay_url = f"https://www.ebay.com/itm/{summary.item_id}"

    body_lines = [
        f"Новый лот по правилу '{watch.name}':",
        f"{summary.title}",
        f"Цена: {price_str} + доставка {ship_str} = всего {total_str}",
        f"Состояние: {summary.condition or 'n/a'}",
        f"Ссылка: {ebay_url}",
    ]

    comment = TaskComment(
        id=str(uuid.uuid4()),
        task_id=task.id,
        author_id=None,
        body="\n".join(body_lines),
        kind="system",
        created_at=now,
    )
    db.add(comment)

    notification = TaskNotification(
        id=str(uuid.uuid4()),
        task_id=task.id,
        user_id=watch.user_id,
        kind="ebay_watch_match",
        status="unread",
        created_at=now,
    )
    db.add(notification)

    logger.info(
        "[watch] New match for watch_id=%s item_id=%s task_id=%s", watch.id, summary.item_id, task.id
    )
