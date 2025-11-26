from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import (
    AiEmailTrainingPair,
    EmailMessage,
    IntegrationAccount,
    IntegrationCredentials,
    IntegrationProvider,
)
from app.services.gmail_client import GmailClient
from app.utils.logger import logger


# Default lookback window for initial sync when last_sync_at is empty.
_DEFAULT_SYNC_LOOKBACK_DAYS = 30
# Max messages to pull per sync cycle for a single account.
_DEFAULT_MAX_MESSAGES_PER_SYNC = 100


def _normalize_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.strip().lower()


def _is_our_outgoing(from_address: Optional[str], account_email: Optional[str]) -> bool:
    if not from_address or not account_email:
        return False
    return _normalize_email(account_email) in from_address.lower()


def _clean_email_text(raw: Optional[str]) -> str:
    """Very simple text cleaner for training pairs.

    - Drops quoted lines starting with '>'.
    - Stops at common reply markers like 'On ... wrote:' or '-----Original Message-----'.
    - Trims leading/trailing whitespace.
    """

    if not raw:
        return ""

    lines = raw.splitlines()
    cleaned: List[str] = []
    stop_markers = [
        "on ",  # e.g. "On Tue, ... wrote:"
        "-----original message-----",
        "пересылаемое сообщение",
    ]

    for line in lines:
        stripped = line.strip("\n\r")
        if not stripped:
            cleaned.append("")
            continue
        if stripped.startswith(">"):
            # Quoted previous thread content.
            continue
        lower = stripped.lower()
        if any(marker in lower for marker in stop_markers) and "wrote:" in lower:
            break
        if "-----original message-----" in lower:
            break
        cleaned.append(stripped)

    text = "\n".join(cleaned).strip()
    return text


def _ensure_gmail_provider(db: Session) -> Optional[IntegrationProvider]:
    return (
        db.query(IntegrationProvider)
        .filter(IntegrationProvider.code == "gmail")
        .one_or_none()
    )


def _load_account_with_credentials(db: Session, account_id: str) -> Tuple[Optional[IntegrationAccount], Optional[IntegrationCredentials]]:
    account: Optional[IntegrationAccount] = (
        db.query(IntegrationAccount)
        .filter(IntegrationAccount.id == account_id)
        .one_or_none()
    )
    if not account:
        return None, None

    creds: Optional[IntegrationCredentials] = (
        db.query(IntegrationCredentials)
        .filter(IntegrationCredentials.integration_account_id == account.id)
        .one_or_none()
    )
    return account, creds


def _build_pairs_for_threads(
    db: Session,
    account: IntegrationAccount,
    thread_ids: List[str],
) -> Dict[str, int]:
    """Build AiEmailTrainingPair rows for the given thread ids.

    Returns a dict with ``pairs_created`` and ``pairs_skipped_existing``.
    """

    pairs_created = 0
    pairs_skipped = 0

    for thread_id in thread_ids:
        if not thread_id:
            continue

        messages: List[EmailMessage] = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.integration_account_id == account.id,
                EmailMessage.thread_id == thread_id,
            )
            .order_by(EmailMessage.sent_at.asc(), EmailMessage.created_at.asc())
            .all()
        )
        if not messages:
            continue

        # Simple heuristic: each incoming message followed by the first
        # outgoing message becomes a pair.
        for idx, msg in enumerate(messages):
            if msg.direction != "incoming":
                continue

            reply: Optional[EmailMessage] = None
            for later in messages[idx + 1 :]:
                if later.direction == "outgoing":
                    reply = later
                    break

            if not reply:
                continue

            existing = (
                db.query(AiEmailTrainingPair)
                .filter(
                    AiEmailTrainingPair.client_message_id == msg.id,
                    AiEmailTrainingPair.our_reply_message_id == reply.id,
                )
                .one_or_none()
            )
            if existing:
                pairs_skipped += 1
                continue

            client_text = _clean_email_text(msg.body_text or msg.body_html or "")
            reply_text = _clean_email_text(reply.body_text or reply.body_html or "")
            if not client_text or not reply_text:
                continue

            pair = AiEmailTrainingPair(
                integration_account_id=account.id,
                thread_id=thread_id,
                client_message_id=msg.id,
                our_reply_message_id=reply.id,
                client_text=client_text,
                our_reply_text=reply_text,
                status="new",
            )
            db.add(pair)
            pairs_created += 1

    return {
        "pairs_created": pairs_created,
        "pairs_skipped_existing": pairs_skipped,
    }


async def sync_gmail_account(
    db: Session,
    account_id: str,
    *,
    manual: bool = False,
    max_messages: int = _DEFAULT_MAX_MESSAGES_PER_SYNC,
) -> Dict[str, Any]:
    """Synchronise a single Gmail IntegrationAccount.

    This function is used both by the background worker and the admin
    "sync-now" endpoint. It is intentionally synchronous w.r.t. the DB
    session (no own SessionLocal) so callers control the transaction
    lifecycle.

    Returns a summary dictionary with keys:

    - account_id
    - messages_fetched
    - messages_upserted
    - pairs_created
    - pairs_skipped_existing
    - errors: list[str]
    """

    provider = _ensure_gmail_provider(db)
    if not provider:
        raise RuntimeError("gmail_provider_not_configured")

    account, creds = _load_account_with_credentials(db, account_id)
    if not account:
        raise RuntimeError("integration_account_not_found")

    if account.provider_id != provider.id:
        raise RuntimeError("integration_account_not_gmail")

    if account.status != "active":
        raise RuntimeError("integration_account_not_active")

    if not creds:
        raise RuntimeError("integration_credentials_missing")

    client = GmailClient(db, account, creds)

    errors: List[str] = []
    messages_fetched = 0
    messages_upserted = 0

    now = datetime.now(timezone.utc)
    since = account.last_sync_at or (now - timedelta(days=_DEFAULT_SYNC_LOOKBACK_DAYS))

    try:
        await client.refresh_access_token_if_needed()
    except Exception as exc:  # pragma: no cover - network failures
        msg = f"token_refresh_failed:{type(exc).__name__}"
        logger.error("[gmail-sync] %s", msg, exc_info=True)
        errors.append(msg)
        account.status = "error"
        db.commit()
        return {
            "account_id": account.id,
            "messages_fetched": 0,
            "messages_upserted": 0,
            "pairs_created": 0,
            "pairs_skipped_existing": 0,
            "errors": errors,
        }

    meta_ids = await client.list_message_ids_since(since, max_results=max_messages)
    messages_fetched = len(meta_ids)

    max_sent_at: Optional[datetime] = account.last_sync_at
    thread_ids: List[str] = []

    for meta in meta_ids:
        try:
            gm = await client.get_message(meta.id)
        except Exception as exc:  # pragma: no cover - defensive
            msg = f"get_message_failed:{meta.id}:{type(exc).__name__}"
            logger.error("[gmail-sync] %s", msg, exc_info=True)
            errors.append(msg)
            continue

        if gm is None:
            continue

        # Determine direction based on From header vs external_account_id.
        direction = (
            "outgoing"
            if _is_our_outgoing(gm.from_address, account.external_account_id)
            else "incoming"
        )

        existing: Optional[EmailMessage] = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.integration_account_id == account.id,
                EmailMessage.external_id == gm.external_id,
            )
            .one_or_none()
        )

        if existing is None:
            existing = EmailMessage(
                integration_account_id=account.id,
                external_id=gm.external_id,
            )
            db.add(existing)

        existing.thread_id = gm.thread_id
        existing.direction = direction
        existing.from_address = gm.from_address
        existing.to_addresses = gm.to_addresses
        existing.cc_addresses = gm.cc_addresses or None
        existing.bcc_addresses = gm.bcc_addresses or None
        existing.subject = gm.subject
        existing.body_text = gm.body_text
        existing.body_html = gm.body_html
        existing.sent_at = gm.sent_at

        messages_upserted += 1

        if gm.sent_at:
            if max_sent_at is None or gm.sent_at > max_sent_at:
                max_sent_at = gm.sent_at
        if gm.thread_id:
            thread_ids.append(gm.thread_id)

    # Build training pairs for all threads that saw new/updated messages.
    pairs_created = 0
    pairs_skipped_existing = 0
    if thread_ids:
        threads_unique = sorted({tid for tid in thread_ids if tid})
        pair_stats = _build_pairs_for_threads(db, account, threads_unique)
        pairs_created = pair_stats["pairs_created"]
        pairs_skipped_existing = pair_stats["pairs_skipped_existing"]

    # Update account bookkeeping and meta summary.
    if max_sent_at:
        account.last_sync_at = max_sent_at
    else:
        account.last_sync_at = now

    meta = dict(account.meta or {})
    meta["last_sync_summary"] = {
        "account_id": account.id,
        "manual": manual,
        "messages_fetched": messages_fetched,
        "messages_upserted": messages_upserted,
        "pairs_created": pairs_created,
        "pairs_skipped_existing": pairs_skipped_existing,
        "errors": errors,
        "finished_at": account.last_sync_at.isoformat() if account.last_sync_at else now.isoformat(),
    }
    account.meta = meta

    db.commit()

    return {
        "account_id": account.id,
        "messages_fetched": messages_fetched,
        "messages_upserted": messages_upserted,
        "pairs_created": pairs_created,
        "pairs_skipped_existing": pairs_skipped_existing,
        "errors": errors,
    }