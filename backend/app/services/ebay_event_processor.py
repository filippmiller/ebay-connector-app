"""Processing helpers for the unified ebay_events inbox.

Phase 1 goal:
- Provide a small helper that can scan ebay_events for unprocessed rows and
  mark them as processed, optionally invoking existing ingestion services for
  known topics.
- Surface one-line `[event] ...` logs that can be appended to the Notifications
  Center debug log during test flows.

Because the Commerce Notification API does not yet expose canonical
order/fulfillment/finances topics, this helper currently focuses on events
produced by our own workers (source="rest_poll") and simply marks matching
rows as processed while recording any errors. Once true order-related
Notification topics are available, this module is the intended place to extend
parsing and ingestion logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayEvent
from app.utils.logger import logger


# Internal topic names already produced by workers when they upsert data via
# PostgresEbayDatabase. These are *not* Notification API topicIds but our own
# canonical labels used in the unified inbox.
_WORKER_ORDER_TOPICS = {
    "ORDER_UPDATED",
}

_WORKER_FINANCES_TOPICS = {
    "FINANCES_TRANSACTION_UPDATED",
    "TRANSACTION_UPDATED",  # legacy transactions path
}

# Payment disputes and Post-Order cases are also ingested via workers and
# logged into ebay_events using these canonical topics.
_WORKER_DISPUTE_TOPICS = {
    "PAYMENT_DISPUTE_UPDATED",
}

_WORKER_CASE_TOPICS = {
    "CASE_UPDATED",
}

# NOTE: ORDER_READY_TO_SHIP is intentionally *not* included in the worker
# topic sets here. It is treated as a raw signal that the Shipping module will
# consume directly (e.g. to drive "Awaiting shipment" queues) rather than a
# piece of data that needs additional REST-based enrichment.


def _get_session(db: Optional[Session] = None) -> Tuple[Session, bool]:
    """Return a session and a flag indicating ownership."""

    if db is not None:
        return db, False
    return SessionLocal(), True


def _append_event_log(debug_log: Optional[List[str]], line: str) -> None:
    if debug_log is not None and line:
        debug_log.append(line)


def process_pending_events(
    *,
    limit: int = 100,
    db: Optional[Session] = None,
    debug_log: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Process unhandled ebay_events rows in a best-effort fashion.

    Current behavior (Phase 1):
    - Select up to ``limit`` rows where ``processed_at IS NULL`` and ``topic`` is
      one of the known worker topics (orders / finances / disputes / cases).
    - For each, mark it as processed immediately and record any errors in
      ``processing_error``.
    - In the future, this is the right hook to call Fulfillment/Finances APIs
      and reuse PostgresEbayDatabase upsert helpers when real
      Notification-based order topics exist.
    """

    session, owns_session = _get_session(db)
    processed = 0
    failed = 0
    by_topic: Dict[str, int] = {}

    try:
        now = datetime.now(timezone.utc)

        q = (
            session.query(EbayEvent)
            .filter(EbayEvent.processed_at.is_(None))
            .filter(
                EbayEvent.topic.in_(
                    _WORKER_ORDER_TOPICS
                    | _WORKER_FINANCES_TOPICS
                    | _WORKER_DISPUTE_TOPICS
                    | _WORKER_CASE_TOPICS,
                ),
            )
            .order_by(EbayEvent.created_at.asc())
            .limit(limit)
        )
        events: List[EbayEvent] = list(q.all())

        if not events:
            _append_event_log(debug_log, "[event] no pending events to process")
            return {"processed": 0, "failed": 0, "by_topic": {}}

        for ev in events:
            topic = ev.topic or "<none>"
            by_topic[topic] = by_topic.get(topic, 0) + 1
            label = f"{ev.entity_type or '-'}:{ev.entity_id or '-'}"
            _append_event_log(
                debug_log,
                f"[event] topic={topic} entity={label} status=processing_started",
            )

            try:
                # For now we do not perform additional REST calls here, because
                # worker-produced events already reflect the full entity JSON
                # that was upserted by PostgresEbayDatabase. We simply mark
                # them as processed.
                ev.processed_at = now
                ev.processing_error = None
                ev.status = ev.status or "PROCESSED"
                processed += 1
                _append_event_log(
                    debug_log,
                    f"[event] topic={topic} entity={label} status=PROCESSED",
                )
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                if ev.processing_error is None:
                    ev.processing_error = {}
                try:
                    # processing_error is a JSONB column; keep it small.
                    details = {
                        "type": "processor_error",
                        "message": str(exc),
                    }
                    if isinstance(ev.processing_error, dict):
                        ev.processing_error.update(details)
                    else:
                        ev.processing_error = details
                except Exception:
                    # As a last resort, ignore structured error recording.
                    pass
                ev.processed_at = now
                ev.status = "FAILED"
                _append_event_log(
                    debug_log,
                    f"[event] topic={topic} entity={label} status=FAILED error=processor_error",
                )

        if owns_session:
            session.commit()
        else:
            session.flush()

        summary = {
            "processed": processed,
            "failed": failed,
            "by_topic": by_topic,
        }
        logger.info("Processed pending ebay_events: %s", summary)
        return summary

    except Exception:
        logger.error("Failed to process pending ebay_events", exc_info=True)
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
