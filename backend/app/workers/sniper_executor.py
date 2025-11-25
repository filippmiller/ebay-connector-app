"""Sniper executor worker (real bidding implementation).

This worker is responsible for:
- polling ebay_snipes for due snipes based on the explicit fire_at timestamp;
- placing a real proxy bid via the eBay Buy Offer API at fire_at;
- marking snipes as BIDDING and recording detailed EbaySnipeLog entries;
- after the auction end_time, querying bidding status and marking snipes as
  WON / LOST / ERROR with result_price and logs.

Lifecycle (Sniper v2):
- scheduled -> bidding -> won / lost / error
- scheduled -> error (when we cannot place a bid)
- bidding -> error (when we cannot fetch bidding status)
"""
from __future__ import annotations

import asyncio
import os
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import (
    EbayAccount,
    EbaySnipe,
    EbaySnipeStatus,
    EbaySnipeLog,
    EbayToken,
)
from app.services.ebay import ebay_service
from app.utils.logger import logger


# Poll interval is configurable via env; default to 1s for precise scheduling.
try:
    POLL_INTERVAL_SECONDS = max(1, int(os.getenv("SNIPER_POLL_INTERVAL_SECONDS", "1")))
except ValueError:  # pragma: no cover - defensive fallback
    POLL_INTERVAL_SECONDS = 1

# Safety cap: maximum number of snipes processed per tick to avoid bursts
# against eBay APIs. Can be overridden via env.
try:
    MAX_SNIPES_PER_TICK = int(os.getenv("SNIPER_MAX_SNIPES_PER_TICK", "50"))
    if MAX_SNIPES_PER_TICK <= 0:
        MAX_SNIPES_PER_TICK = 50
except ValueError:  # pragma: no cover - defensive fallback
    MAX_SNIPES_PER_TICK = 50


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _pick_due_snipes(db: Session, now: datetime) -> List[EbaySnipe]:
    """Return snipes whose fire_at has passed but auction has not ended.

    This uses the explicit fire_at column computed at creation/update time
    instead of re-deriving the schedule expression on every tick.
    """

    q = (
        db.query(EbaySnipe)
        .filter(
            EbaySnipe.status == EbaySnipeStatus.scheduled.value,
            EbaySnipe.fire_at <= now,
            EbaySnipe.end_time > now,
        )
        .order_by(EbaySnipe.fire_at.asc())
        .limit(MAX_SNIPES_PER_TICK)
    )

    return list(q.all())


def _pick_ended_bidding_snipes(db: Session, now: datetime) -> List[EbaySnipe]:
    """Return snipes whose auctions have ended and which are in BIDDING state.

    These are candidates for a result check via the Buy Offer getBidding
    endpoint to determine WON/LOST state and final price.
    """

    q = (
        db.query(EbaySnipe)
        .filter(
            EbaySnipe.status == EbaySnipeStatus.bidding.value,
            EbaySnipe.end_time <= now,
        )
        .order_by(EbaySnipe.end_time.asc())
    )

    return list(q.all())


def _resolve_account_and_token(db: Session, snipe: EbaySnipe) -> Tuple[Optional[EbayAccount], Optional[str], Optional[str]]:
    """Resolve EbayAccount + decrypted OAuth access token for a snipe.

    Returns (account, access_token, error_message). When error_message is not
    None, either account or access_token may be None and the caller should
    treat the whole operation as a business failure.
    """

    if not snipe.ebay_account_id:
        return None, None, "Snipe has no ebay_account_id configured"

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == snipe.ebay_account_id)
        .one_or_none()
    )
    if account is None:
        return None, None, f"eBay account {snipe.ebay_account_id} not found"

    token_row: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(EbayToken.updated_at.desc())
        .first()
    )
    access_token = token_row.access_token if token_row else None  # type: ignore[union-attr]
    if not access_token:
        return account, None, f"No active eBay token for account id={account.id} (username={account.username})"

    return account, access_token, None


async def _resolve_rest_item_id(access_token: str, legacy_item_id: str) -> str:
    """Resolve the RESTful item id from a legacy numeric ItemID via Browse API.

    The Sniper UI stores legacy ItemIDs; Buy Offer APIs require the REST-style
    item id used by Browse/Inventory (e.g. ``v1|1234567890|0``). This helper is
    intentionally narrow and only returns the itemId field.
    """

    base_url = settings.ebay_api_base_url.rstrip("/")
    url = f"{base_url}/buy/browse/v1/item/get_item_by_legacy_id"
    params = {"legacy_item_id": legacy_item_id}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        # Use literal HTTP status codes to avoid depending on fastapi.status
        raise HTTPException(
            status_code=502,
            detail=f"Failed to contact eBay Browse API for legacy_item_id={legacy_item_id}: {exc}",
        )

    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {"message": resp.text[:500]}
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Failed to resolve REST item id from legacy ItemID",
                "status": resp.status_code,
                "body": body,
            },
        )

    data = resp.json() or {}
    rest_item_id = data.get("itemId")
    if not rest_item_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Browse API response is missing itemId field; cannot place bid",
        )

    return str(rest_item_id)


async def _place_bid_for_snipe(db: Session, snipe: EbaySnipe, now: datetime) -> None:
    """Place a real proxy bid for a due snipe via Buy Offer API.

    On success, marks the snipe as BIDDING and records a log entry. On error,
    marks status=ERROR and logs the failure while keeping the row for
    inspection.
    """

    # Safety guardrails before doing any external calls.
    # 1) Max bid must be positive.
    if snipe.max_bid_amount is None or snipe.max_bid_amount <= 0:
        snipe.status = EbaySnipeStatus.error.value
        snipe.has_bid = False
        snipe.result_message = "Skipped: invalid max_bid_amount (must be > 0)"
        snipe.updated_at = now
        logger.warning(
            "Sniper executor: skipping snipe id=%s due to invalid max_bid_amount=%s",
            snipe.id,
            snipe.max_bid_amount,
        )
        db.add(
            EbaySnipeLog(
                snipe_id=snipe.id,
                event_type="skipped_invalid_max_bid",
                status=EbaySnipeStatus.error.value,
                http_status=None,
                payload=None,
                message=snipe.result_message,
            )
        )
        return

    # 2) If we are already too close to end_time, do not attempt a bid.
    if snipe.end_time is not None:
        remaining_seconds = (snipe.end_time - now).total_seconds()
        if remaining_seconds < 1.0:
            snipe.status = EbaySnipeStatus.error.value
            snipe.has_bid = False
            snipe.result_message = (
                "Skipped: too late to bid (end_time is in "
                f"{remaining_seconds:.3f} seconds)"
            )
            snipe.updated_at = now
            logger.warning(
                "Sniper executor: skipping snipe id=%s because it is too late to bid (remaining_seconds=%.3f)",
                snipe.id,
                remaining_seconds,
            )
            db.add(
                EbaySnipeLog(
                    snipe_id=snipe.id,
                    event_type="skipped_too_late",
                    status=EbaySnipeStatus.error.value,
                    http_status=None,
                    payload=None,
                    message=snipe.result_message,
                )
            )
            return

    account, access_token, error_msg = _resolve_account_and_token(db, snipe)
    if error_msg or not account or not access_token:
        snipe.status = EbaySnipeStatus.error.value
        snipe.has_bid = True
        snipe.result_message = error_msg or "Missing eBay account/token for sniper execution"
        snipe.updated_at = now
        db.add(
            EbaySnipeLog(
                snipe_id=snipe.id,
                event_type="place_bid_error",
                status=EbaySnipeStatus.error.value,
                http_status=None,
                payload=None,
                message=snipe.result_message,
            )
        )
        return

    try:
        rest_item_id = await _resolve_rest_item_id(access_token, snipe.item_id)
    except HTTPException as exc:
        snipe.status = EbaySnipeStatus.error.value
        snipe.has_bid = True
        snipe.result_message = str(exc.detail)
        snipe.updated_at = now
        db.add(
            EbaySnipeLog(
                snipe_id=snipe.id,
                event_type="place_bid_error",
                status=EbaySnipeStatus.error.value,
                http_status=exc.status_code,
                payload=json.dumps(exc.detail) if isinstance(exc.detail, (dict, list, str)) else None,
                message=snipe.result_message,
            )
        )
        return

    currency = (snipe.currency or "USD").upper()
    max_amount = snipe.max_bid_amount or Decimal("0")
    max_amount_str = str(max_amount)
    marketplace_id = getattr(account, "marketplace_id", None) or "EBAY_US"

    try:
        payload = await ebay_service.place_proxy_bid(
            access_token=access_token,
            item_id=rest_item_id,
            max_amount_value=max_amount_str,
            currency=currency,
            marketplace_id=marketplace_id,
        )
    except HTTPException as exc:
        snipe.status = EbaySnipeStatus.error.value
        snipe.has_bid = True
        snipe.result_message = str(exc.detail)
        snipe.updated_at = now
        db.add(
            EbaySnipeLog(
                snipe_id=snipe.id,
                event_type="place_bid_error",
                status=EbaySnipeStatus.error.value,
                http_status=exc.status_code,
                payload=json.dumps(exc.detail) if isinstance(exc.detail, (dict, list, str)) else None,
                message=snipe.result_message,
            )
        )
        return

    proxy_bid_id = None
    if isinstance(payload, dict):
        proxy_bid_id = payload.get("proxyBidId") or payload.get("bidId")

    snipe.status = EbaySnipeStatus.bidding.value
    snipe.has_bid = True
    snipe.updated_at = now
    snipe.result_message = (
        f"Proxy bid placed (max {max_amount_str} {currency}) via Buy Offer API"
    )

    db.add(
        EbaySnipeLog(
            snipe_id=snipe.id,
            event_type="place_bid",
            status=EbaySnipeStatus.bidding.value,
            ebay_bid_id=str(proxy_bid_id) if proxy_bid_id else None,
            http_status=200,
            payload=json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload),
            message=snipe.result_message,
        )
    )


async def _finalize_ended_snipes(db: Session, now: datetime) -> int:
    """Check ended auctions in BIDDING state and mark them WON/LOST/ERROR."""

    snipes = _pick_ended_bidding_snipes(db, now)
    if not snipes:
        return 0

    processed = 0
    for snipe in snipes:
        account, access_token, error_msg = _resolve_account_and_token(db, snipe)
        if error_msg or not account or not access_token:
            snipe.status = EbaySnipeStatus.error.value
            snipe.result_message = error_msg or "Missing eBay account/token for result check"
            snipe.updated_at = now
            db.add(
                EbaySnipeLog(
                    snipe_id=snipe.id,
                    event_type="result_check_error",
                    status=EbaySnipeStatus.error.value,
                    http_status=None,
                    payload=None,
                    message=snipe.result_message,
                )
            )
            processed += 1
            continue

        try:
            rest_item_id = await _resolve_rest_item_id(access_token, snipe.item_id)
        except HTTPException as exc:
            snipe.status = EbaySnipeStatus.error.value
            snipe.result_message = str(exc.detail)
            snipe.updated_at = now
            db.add(
                EbaySnipeLog(
                    snipe_id=snipe.id,
                    event_type="result_check_error",
                    status=EbaySnipeStatus.error.value,
                    http_status=exc.status_code,
                    payload=json.dumps(exc.detail) if isinstance(exc.detail, (dict, list, str)) else None,
                    message=snipe.result_message,
                )
            )
            processed += 1
            continue

        marketplace_id = getattr(account, "marketplace_id", None) or "EBAY_US"
        try:
            payload = await ebay_service.get_bidding_status(
                access_token=access_token,
                item_id=rest_item_id,
                marketplace_id=marketplace_id,
            )
        except HTTPException as exc:
            snipe.status = EbaySnipeStatus.error.value
            snipe.result_message = str(exc.detail)
            snipe.updated_at = now
            db.add(
                EbaySnipeLog(
                    snipe_id=snipe.id,
                    event_type="result_check_error",
                    status=EbaySnipeStatus.error.value,
                    http_status=exc.status_code,
                    payload=json.dumps(exc.detail) if isinstance(exc.detail, (dict, list, str)) else None,
                    message=snipe.result_message,
                )
            )
            processed += 1
            continue

        auction_status = None
        high_bidder = None
        current_price_value: Optional[Decimal] = None
        if isinstance(payload, dict):
            auction_status = payload.get("auctionStatus")
            high_bidder = payload.get("highBidder")
            current_price = payload.get("currentPrice") or {}
            try:
                if current_price.get("value") is not None:
                    current_price_value = Decimal(str(current_price.get("value")))
            except Exception:  # pragma: no cover - defensive
                current_price_value = None

        message = None
        if auction_status == "ENDED":
            if high_bidder:
                snipe.status = EbaySnipeStatus.won.value
                message = "Auction ended: WON"
            else:
                snipe.status = EbaySnipeStatus.lost.value
                message = "Auction ended: LOST"
        else:
            # Auction not yet ended or status unknown – leave as bidding.
            message = f"Auction status from getBidding: {auction_status or 'UNKNOWN'}"

        if current_price_value is not None:
            snipe.result_price = current_price_value
        if message:
            snipe.result_message = message
        snipe.updated_at = now

        db.add(
            EbaySnipeLog(
                snipe_id=snipe.id,
                event_type="result_check",
                status=snipe.status,
                http_status=200,
                payload=json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload),
                message=message,
            )
        )
        processed += 1

    return processed


async def run_sniper_once() -> int:
    """Run a single sniper evaluation tick.

    Returns the number of snipes processed.
    """

    db: Session = SessionLocal()
    processed = 0
    now = _now_utc()
    try:
        # 1) Execute due snipes by placing real proxy bids.
        snipes = _pick_due_snipes(db, now)
        if snipes:
            logger.info("Sniper executor: found %d due snipes", len(snipes))
            for s in snipes:
                try:
                    await _place_bid_for_snipe(db, s, now)
                    processed += 1
                except Exception as exc:  # pragma: no cover - safety net
                    logger.error(
                        "Sniper executor: failed to place bid for snipe id=%s: %s", s.id, exc, exc_info=True
                    )

        # 2) Finalize results for ended auctions in BIDDING state.
        processed += await _finalize_ended_snipes(db, now)

        db.commit()
        return processed
    finally:
        db.close()


async def run_sniper_loop(interval_seconds: int = POLL_INTERVAL_SECONDS) -> None:
    """Background loop for the sniper executor.

    Designed to be run as a standalone worker process (e.g. Railway service).
    """

    logger.info("Sniper executor loop started (interval=%s seconds)", interval_seconds)

    while True:
        try:
            count = await run_sniper_once()
            if count:
                logger.info("Sniper executor: processed %d snipes in this tick", count)
        except Exception as exc:  # pragma: no cover - safety net
            logger.error("Sniper executor loop error: %s", exc, exc_info=True)

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":  # pragma: no cover - manual run helper
    asyncio.run(run_sniper_loop())