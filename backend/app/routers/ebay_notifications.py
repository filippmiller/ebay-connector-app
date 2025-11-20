from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

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

    try:
        raw_body = await request.body()
        payload: Dict[str, Any]
        if not raw_body:
            payload = {}
        else:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="invalid_json_body")

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
            status="RECEIVED",
            error=None,
            signature_valid=signature_valid,
            signature_kid=signature_kid,
        )

        # Per Notification API requirements, any 2xx indicates success; we
        # intentionally return an empty 204 response body.
        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Unhandled error in eBay events webhook: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="internal_error")


@router.get("/events")
async def ebay_events_challenge_placeholder() -> Dict[str, str]:
    """Placeholder for Notification API destination challenge handling.

    eBay may call this endpoint with a challenge payload when validating a
    destination. Proper cryptographic handling will be wired in a follow-up
    change; for now we expose a no-op endpoint so the route exists.
    """

    # TODO: Implement real destination challenge verification per eBay docs.
    return {"status": "not_implemented", "message": "Notification challenge handling will be implemented separately."}
