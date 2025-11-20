from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response, JSONResponse
from app.services.ebay_event_inbox import log_ebay_event
from app.utils.logger import logger


router = APIRouter(prefix="/webhooks/ebay", tags=["ebay_webhooks"])


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
        parse_error: str | None = None
        if not raw_body:
            payload = {}
        else:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                payload = {"_raw": raw_body.decode("utf-8", errors="replace")}
                parse_error = f"invalid_json_body: {exc}"

        # Handle potential POST-based challenge payloads from Notification API.
        if isinstance(payload, dict) and "challenge" in payload and not payload.get("notification") and not payload.get("metadata"):
            challenge_value = str(payload.get("challenge"))
            logger.info("Received eBay notification POST challenge=%s", challenge_value)
            return JSONResponse({"challengeResponse": challenge_value})

        # Normalize headers (lower-case keys for consistency)
        headers = {k.lower(): v for k, v in request.headers.items()}

        source = "notification"
        channel = "commerce_notification"
        topic = None
        event_time = None
        publish_time = None

        if isinstance(payload, dict):
            metadata = payload.get("metadata") or {}
            notification = payload.get("notification") or {}

            if isinstance(metadata, dict):
                topic = metadata.get("topic")

            if isinstance(notification, dict):
                event_time = notification.get("eventDate")
                publish_time = notification.get("publishDate")

        # Extract signature_kid from X-EBAY-SIGNATURE header if present.
        signature_kid = None
        signature_valid = None  # TODO: integrate real signature verification when utility is available.

        sig_header = headers.get("x-ebay-signature")
        if sig_header:
            try:
                sig_obj = json.loads(sig_header)
                if isinstance(sig_obj, dict) and sig_obj.get("kid") is not None:
                    signature_kid = str(sig_obj["kid"])
            except Exception:
                logger.warning("Failed to parse X-EBAY-SIGNATURE header", exc_info=True)

        # Persist normalized event row. We keep entity_type / entity_id / ebay_account
        # empty for now; processors will enrich them later.
        status_value = "FAILED" if parse_error else "RECEIVED"
        error_value = parse_error or None

        try:
            log_ebay_event(
                source=source,
                channel=channel,
                topic=topic,
                entity_type=None,
                entity_id=None,
                ebay_account=None,
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
    challenge_code: str | None = Query(None, alias="challengeCode"),
) -> Dict[str, str]:
    """Handle Notification API destination challenge (minimal implementation).

    When a destination is (re)configured, eBay may send a challenge request with
    a ``challengeCode`` query parameter. The expected response is a JSON body
    with ``challengeResponse`` echoing the same value. We do not yet perform
    any additional signature validation here; that will be wired separately.
    """

    if challenge_code:
        logger.info("Received eBay notification challengeCode=%s", challenge_code)
        return {"challengeResponse": challenge_code}

    return {"status": "ok", "message": "No challengeCode provided"}
