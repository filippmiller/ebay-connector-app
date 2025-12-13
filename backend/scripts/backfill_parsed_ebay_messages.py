import os
import math
import sys
from typing import Any, Dict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure "backend" package root is on sys.path when script is invoked
# as "python scripts/backfill_parsed_ebay_messages.py" from the backend dir.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(CURRENT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.models_sqlalchemy.models import Message as SqlMessage
from app.ebay.message_body_parser import parse_ebay_message_body
from app.services.message_parser import parse_ebay_message_html
from app.utils.logger import logger


BATCH_SIZE = 500


def backfill() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)

    logger.info("Starting backfill_parsed_ebay_messages")

    with engine.begin() as conn:
        total = conn.execute(
            text(
                "SELECT count(*) FROM ebay_messages "
                "WHERE parsed_body IS NULL "
                "   OR case_id IS NULL "
                "   OR transaction_id IS NULL "
                "   OR message_topic IS NULL "
                "   OR preview_text IS NULL"
            )
        ).scalar() or 0

    if total == 0:
        logger.info("No ebay_messages rows require backfill; exiting")
        return

    logger.info("Backfill will process %s messages in batches of %s", total, BATCH_SIZE)

    processed = 0
    updated = 0
    with SessionLocal() as session:
        pages = int(math.ceil(total / BATCH_SIZE))
        for page in range(pages):
            rows = (
                session.query(SqlMessage)
                .order_by(SqlMessage.created_at)
                .offset(page * BATCH_SIZE)
                .limit(BATCH_SIZE)
                .all()
            )
            if not rows:
                break

            for msg in rows:
                processed += 1
                body_html = msg.body or ""
                if not body_html:
                    continue

                parsed_body: Dict[str, Any] | None = msg.parsed_body or None
                normalized: Dict[str, Any] = {}

                # Rich parser used by /messages grid
                try:
                    rich = parse_ebay_message_html(
                        body_html,
                        our_account_username=msg.recipient_username or "seller",
                    )
                    rich_dict = rich.dict(exclude_none=True)
                    parsed_body = parsed_body or {}
                    parsed_body.update(rich_dict)
                except Exception as exc:
                    logger.warning(
                        "Backfill: failed rich parse for message id=%s: %s",
                        msg.id,
                        exc,
                    )

                # Normalized view
                try:
                    normalized_body = parse_ebay_message_body(
                        body_html,
                        our_account_username=msg.recipient_username or "seller",
                    )
                    norm = normalized_body.get("normalized") or {}
                    normalized = norm
                    parsed_body = parsed_body or {}
                    if norm:
                        parsed_body["normalized"] = norm
                except Exception as exc:
                    logger.warning(
                        "Backfill: failed normalized parse for message id=%s: %s",
                        msg.id,
                        exc,
                    )

                # Map normalized fields into columns
                changed = False
                if parsed_body is not None and parsed_body != msg.parsed_body:
                    msg.parsed_body = parsed_body
                    changed = True

                if normalized:
                    if not msg.case_id and normalized.get("caseId"):
                        msg.case_id = normalized.get("caseId")
                        changed = True
                    if not msg.inquiry_id and normalized.get("inquiryId"):
                        msg.inquiry_id = normalized.get("inquiryId")
                        changed = True
                    if not msg.return_id and normalized.get("returnId"):
                        msg.return_id = normalized.get("returnId")
                        changed = True
                    if not msg.payment_dispute_id and normalized.get("paymentDisputeId"):
                        msg.payment_dispute_id = normalized.get("paymentDisputeId")
                        changed = True
                    if not msg.order_id and normalized.get("orderId"):
                        msg.order_id = normalized.get("orderId")
                        changed = True
                    if not msg.listing_id and normalized.get("itemId"):
                        msg.listing_id = normalized.get("itemId")
                        changed = True
                    if not msg.transaction_id and normalized.get("transactionId"):
                        msg.transaction_id = normalized.get("transactionId")
                        changed = True

                    topic = normalized.get("topic")
                    if topic and msg.message_topic != topic:
                        msg.message_topic = topic
                        changed = True
                        if topic in {"CASE", "RETURN", "INQUIRY", "PAYMENT_DISPUTE"}:
                            msg.is_case_related = True

                    if not msg.preview_text:
                        preview = normalized.get("summaryText")
                        if preview:
                            msg.preview_text = preview
                            changed = True

                    attachments = normalized.get("attachments") or []
                    if isinstance(attachments, list) and attachments:
                        if not msg.has_attachments:
                            msg.has_attachments = True
                            changed = True
                        if not msg.attachments_meta:
                            msg.attachments_meta = attachments
                            changed = True

                if changed:
                    updated += 1

            session.commit()
            logger.info(
                "Backfill batch %s/%s: processed=%s, updated=%s so far",
                page + 1,
                pages,
                processed,
                updated,
            )

    logger.info("Backfill completed: processed=%s, updated=%s", processed, updated)


if __name__ == "__main__":
    backfill()
