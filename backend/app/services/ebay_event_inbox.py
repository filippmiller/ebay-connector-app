from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayEvent
from app.utils.logger import logger


DatetimeLike = Union[str, datetime, None]


def _parse_datetime(value: DatetimeLike) -> Optional[datetime]:
    """Best-effort ISO8601 → timezone-aware datetime parser.

    Accepts either a datetime instance (returned as-is) or a string such as
    "2024-01-01T12:34:56Z" / "2024-01-01T12:34:56+00:00".
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    s = str(value).strip()
    if not s:
        return None

    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        logger.warning("Failed to parse event datetime '%s'", value)
        return None


def log_ebay_event(
    *,
    source: str,
    channel: str,
    topic: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    ebay_account: Optional[str] = None,
    event_time: DatetimeLike = None,
    publish_time: DatetimeLike = None,
    headers: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    status: str = "RECEIVED",
    error: Optional[str] = None,
    signature_valid: Optional[bool] = None,
    signature_kid: Optional[str] = None,
    db: Optional[Session] = None,
) -> EbayEvent:
    """Insert a normalized row into ebay_events.

    This helper is the single entry point for all eBay event producers
    (Notification API webhooks, Trading/REST pollers, manual tests, etc.).
    
    Args:
        source: Logical source on our side (notification, rest_poll, trading_poll, ...).
        channel: API family / channel (commerce_notification, sell_fulfillment_api, ...).
        topic: Event topic/type (MARKETPLACE_ACCOUNT_DELETION, ORDER_UPDATED, ...).
        entity_type: High-level entity type (ORDER, MESSAGE, OFFER, ...).
        entity_id: Primary identifier of the entity (orderId, messageId, ...).
        ebay_account: Seller account identifier (username / ebay_user_id / house name).
        event_time: Business time when the event occurred (if known).
        publish_time: Time when eBay published the event (if known).
        headers: HTTP headers for webhooks, or synthetic metadata for pollers.
        payload: Full raw payload object for this event.
        status: Processing status on our side (default RECEIVED).
        error: Optional error description for FAILED/IGNORED events.
        signature_valid: Result of Notification API signature validation, if checked.
        signature_kid: Key ID extracted from X-EBAY-SIGNATURE, if present.
        db: Optional existing SQLAlchemy session; if omitted, a short-lived
            session is created for this insert.
    """

    owns_session = False
    session: Session

    if db is None:
        session = SessionLocal()
        owns_session = True
    else:
        session = db

    try:
        ev = EbayEvent(
            source=source,
            channel=channel,
            topic=topic,
            entity_type=entity_type,
            entity_id=entity_id,
            ebay_account=ebay_account,
            event_time=_parse_datetime(event_time),
            publish_time=_parse_datetime(publish_time),
            status=status or "RECEIVED",
            error=error,
            headers=headers or {},
            signature_valid=signature_valid,
            signature_kid=signature_kid,
            payload=payload or {},
        )

        session.add(ev)
        if owns_session:
            session.commit()
            session.refresh(ev)
        else:
            # Let the caller control transaction boundaries; we still flush so
            # that the insert is staged for commit.
            session.flush()
        return ev

    except Exception:
        logger.error("Failed to log eBay event (source=%s, channel=%s, topic=%s)", source, channel, topic, exc_info=True)
        session.rollback()
        raise

    finally:
        if owns_session:
            session.close()
