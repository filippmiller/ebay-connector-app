from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response, JSONResponse
from app.config import settings
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount
from app.services.ebay_event_inbox import log_ebay_event
from app.services.ebay_signature import verify_ebay_notification_signature
from app.utils.logger import logger


router = APIRouter(prefix="/webhooks/ebay", tags=["ebay_webhooks"])


def _compute_challenge_response(challenge_code: str) -> str:
    """Compute Marketplace Account Deletion challengeResponse.

    Per eBay docs, the value is:
        hex_sha256(challengeCode + verificationToken + endpointUrl)
    where endpointUrl MUST exactly match the destination endpoint registered
    with Notification API and in the eBay Dev Portal.
    """

    verification_token = settings.EBAY_NOTIFICATION_VERIFICATION_TOKEN
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL

    if not verification_token or not endpoint_url:
        logger.error(
            "Cannot compute eBay challengeResponse: missing verification token or destination URL",
        )
        raise HTTPException(
            status_code=500,
            detail="Notification challenge configuration is incomplete on the server.",
        )

    raw = f"{challenge_code}{verification_token}{endpoint_url}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    logger.info(
        "[challenge] computed challengeResponse for endpoint=%s challengeCode=%s",
        endpoint_url,
        challenge_code,
    )
    return digest


@router.post("/events", status_code=204)
async def ebay_events_webhook(request: Request) -> Response:
    """Notification API destination endpoint used by eBay to push events.

    This handler accepts the generic Notification API JSON envelope and stores
    a normalized row in ebay_events. It is intentionally minimal for now and
    does not perform any business processing.
    """

    # We deliberately avoid propagating JSON parsing errors back to eBay.
    # Instead, we best-effort capture whatever we can and always return 2xx,
    # so that eBay does not mark the destination as unhealthy while we debug.
    raw_body: bytes = b""
    try:
        raw_body = await request.body()
        payload: Dict[str, Any]
        parse_error: Optional[str] = None
        if not raw_body:
            payload = {}
        else:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                payload = {"_raw": raw_body.decode("utf-8", errors="replace")}
                parse_error = f"invalid_json_body: {exc}"

        # Handle potential POST-based challenge payloads from Notification API.
        if isinstance(payload, dict) and not payload.get("notification") and not payload.get("metadata"):
            challenge_value = (
                payload.get("challengeCode")
                or payload.get("challenge_code")
                or payload.get("challenge")
            )
            if challenge_value:
                challenge_str = str(challenge_value)
                logger.info("[challenge] Received eBay POST challenge challengeCode=%s", challenge_str)
                response_value = _compute_challenge_response(challenge_str)
                return JSONResponse({"challengeResponse": response_value})

        # Normalize headers for storage. Keys are lower-cased and sensitive
        # values (Authorization, *token*, *secret*) are redacted so that
        # ebay_events.headers never leaks secrets.
        headers: Dict[str, Any] = {}
        for k, v in request.headers.items():
            lk = k.lower()
            if lk == "authorization" or "token" in lk or "secret" in lk:
                headers[lk] = "***REDACTED***"
            else:
                headers[lk] = v

        source = "notification"
        channel = "commerce_notification"
        topic: Optional[str] = None
        event_time: Optional[str] = None
        publish_time: Optional[str] = None
        entity_type: Optional[str] = None
        entity_id: Optional[str] = None
        ebay_account_value: Optional[str] = None
        account_note: Optional[str] = None

        if isinstance(payload, dict):
            metadata = payload.get("metadata") or {}
            notification = payload.get("notification") or {}

            if isinstance(metadata, dict):
                topic = metadata.get("topic")

            if isinstance(notification, dict):
                event_time = notification.get("eventDate")
                publish_time = notification.get("publishDate")

                # Topic-aware entity extraction for core Commerce Notification topics.
                data = notification.get("data") or {}
                if topic == "MARKETPLACE_ACCOUNT_DELETION":
                    # ACCOUNT-level event; try to extract a stable account identifier.
                    account_info = data.get("account") or data.get("seller") or {}
                    username = account_info.get("username") or account_info.get("login")
                    account_id = account_info.get("accountId") or account_info.get("userId")
                    entity_type = "ACCOUNT"
                    entity_id = username or account_id or None

                    # Best-effort internal EbayAccount resolution so that the grid
                    # can group events by house/account. Failure here is non-fatal.
                    try:
                        if username or account_id:
                            session = SessionLocal()
                            try:
                                q = session.query(EbayAccount)
                                if username and account_id:
                                    q = q.filter(
                                        (EbayAccount.username == username)
                                        | (EbayAccount.ebay_user_id == account_id),
                                    )
                                elif username:
                                    q = q.filter(EbayAccount.username == username)
                                else:
                                    q = q.filter(EbayAccount.ebay_user_id == account_id)
                                acc = q.first()
                                if acc is not None:
                                    ebay_account_value = acc.username or acc.ebay_user_id or acc.house_name
                                else:
                                    account_note = (
                                        f"account_lookup_failed: no EbayAccount for username={username!r} "
                                        f"or ebay_user_id={account_id!r}"
                                    )
                            finally:
                                session.close()
                    except Exception:
                        logger.warning(
                            "Failed to resolve EbayAccount for MAD webhook username=%s accountId=%s",
                            username,
                            account_id,
                            exc_info=True,
                        )
                        # Do not treat this as a hard failure; just record a note.
                        if not account_note:
                            account_note = "account_lookup_failed: exception during resolution"

                elif topic == "NEW_MESSAGE":
                    # Messaging event; try to extract message/thread identifiers.
                    message = data.get("message") or data
                    msg_id = (
                        message.get("messageId")
                        or message.get("id")
                        or message.get("message_id")
                    )
                    thread_id = (
                        message.get("threadId")
                        or message.get("conversationId")
                        or message.get("thread_id")
                    )
                    entity_type = "MESSAGE"
                    entity_id = msg_id or thread_id or None

                    # Best-effort account resolution from any seller/account block.
                    seller_info = data.get("seller") or data.get("account") or {}
                    username = seller_info.get("username") or seller_info.get("login")
                    ebay_user_id = seller_info.get("userId") or seller_info.get("accountId")
                    try:
                        if username or ebay_user_id:
                            session = SessionLocal()
                            try:
                                q = session.query(EbayAccount)
                                if username and ebay_user_id:
                                    q = q.filter(
                                        (EbayAccount.username == username)
                                        | (EbayAccount.ebay_user_id == ebay_user_id),
                                    )
                                elif username:
                                    q = q.filter(EbayAccount.username == username)
                                else:
                                    q = q.filter(EbayAccount.ebay_user_id == ebay_user_id)
                                acc = q.first()
                                if acc is not None:
                                    ebay_account_value = acc.username or acc.ebay_user_id or acc.house_name
                                else:
                                    account_note = (
                                        f"account_lookup_failed: no EbayAccount for username={username!r} "
                                        f"or ebay_user_id={ebay_user_id!r}"
                                    )
                            finally:
                                session.close()
                    except Exception:
                        logger.warning(
                            "Failed to resolve EbayAccount for NEW_MESSAGE webhook username=%s ebay_user_id=%s",
                            username,
                            ebay_user_id,
                            exc_info=True,
                        )
                        if not account_note:
                            account_note = "account_lookup_failed: exception during resolution"

        # Extract and (best-effort) verify X-EBAY-SIGNATURE header when present.
        signature_kid: Optional[str] = None
        signature_valid: Optional[bool] = None
        sig_error: Optional[dict] = None

        raw_sig_header = request.headers.get("X-EBAY-SIGNATURE") or request.headers.get("x-ebay-signature")
        if raw_sig_header:
            is_valid, kid, err = await verify_ebay_notification_signature(raw_sig_header, raw_body)
            signature_kid = kid
            signature_valid = is_valid
            sig_error = err

        # Persist normalized event row. For now, business processing happens in
        # downstream workers; this endpoint focuses on durable, debuggable
        # storage of Notification events.
        status_value = "FAILED" if parse_error else "RECEIVED"
        error_parts: list[str] = []
        if parse_error:
            error_parts.append(parse_error)
        if sig_error and sig_error.get("type"):
            error_parts.append(f"signature_error:{sig_error['type']}")
        if account_note:
            error_parts.append(account_note)
        error_value = "; ".join(error_parts) if error_parts else None

        try:
            log_ebay_event(
                source=source,
                channel=channel,
                topic=topic,
                entity_type=entity_type,
                entity_id=entity_id,
                ebay_account=ebay_account_value,
                event_time=event_time,
                publish_time=publish_time,
                headers=headers,
                payload=payload,
                status=status_value,
                error=error_value,
                signature_valid=signature_valid,
                signature_kid=signature_kid,
            )
        except Exception:
            # Even if logging fails (e.g. DB outage), we *still* return 2xx so
            # that eBay does not start backing off the destination. The error is
            # recorded in application logs for investigation.
            logger.error("Failed to persist ebay_events row for webhook", exc_info=True)

        # Per Notification API requirements, any 2xx indicates success; we
        # intentionally return an empty 204 response body.
        return Response(status_code=204)

    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Unhandled error in eBay events webhook: %s", exc, exc_info=True)
        # Best-effort log a FAILED event with minimal context.
        try:
            log_ebay_event(
                source="notification",
                channel="commerce_notification",
                topic=None,
                entity_type=None,
                entity_id=None,
                ebay_account=None,
                event_time=None,
                publish_time=None,
                headers={k.lower(): v for k, v in request.headers.items()},
                payload={"_raw": raw_body.decode("utf-8", errors="replace")} if raw_body else {},
                status="FAILED",
                error=f"unhandled_error: {exc}",
                signature_valid=None,
                signature_kid=None,
            )
        except Exception:
            logger.error("Failed to persist FAILED ebay_events row after unhandled error", exc_info=True)

        # Still return 2xx to keep destination healthy from eBay's perspective.
        return Response(status_code=204)


@router.get("/events")
async def ebay_events_challenge(
    challenge_code_q: str | None = Query(None, alias="challenge_code"),
    challenge_code_camel: str | None = Query(None, alias="challengeCode"),
) -> Dict[str, str]:
    """Handle Notification API destination challenge (GET variant).

    eBay may send either ``challenge_code`` or ``challengeCode`` as the query
    parameter name. We support both and compute the Marketplace Account
    Deletion challengeResponse using the configured verification token and
    destination URL.
    """

    code = challenge_code_q or challenge_code_camel
    if code:
        logger.info("[challenge] Received eBay GET challenge challengeCode=%s", code)
        response_value = _compute_challenge_response(code)
        return {"challengeResponse": response_value}

    return {"status": "ok", "message": "No challenge code provided"}
