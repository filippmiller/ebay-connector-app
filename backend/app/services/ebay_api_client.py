"""Lightweight eBay Browse/Search API client used by the monitoring worker.

This module intentionally keeps the surface area small: it exposes a single
function to search active listings by keyword using an OAuth access token
obtained elsewhere (EbayToken or application token).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import asyncio
import httpx

from fastapi import HTTPException, status

from app.config import settings
from app.utils.logger import logger


@dataclass
class EbayListingSummary:
    """Normalized subset of eBay Browse API item summary fields."""

    item_id: str
    title: str
    price: float
    shipping: float
    condition: Optional[str]
    description: Optional[str]


async def search_active_listings(
    access_token: str,
    keywords: str,
    *,
    limit: int = 20,
) -> List[EbayListingSummary]:
    """Search active listings for the given keywords via the Browse API.

    This function uses the Buy Browse API `item_summary/search` endpoint.
    It is intentionally conservative: on any HTTP or parsing error it logs
    and returns an empty list so the monitoring worker can continue.
    """

    keywords = (keywords or "").strip()
    if not access_token or not keywords:
        return []

    base = settings.ebay_api_base_url.rstrip("/")
    url = f"{base}/buy/browse/v1/item_summary/search"

    params = {
        "q": keywords,
        # Limit the number of results per model to avoid flooding candidates.
        "limit": str(max(1, min(limit, 50))),
        # Prefer newly listed and active items first.
        "sort": "NEWLY_LISTED",
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        # Default marketplace; can be extended in the future if we add
        # per-account marketplace routing.
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            resp = await client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:  # pragma: no cover - network dependent
        logger.error("Browse API request error: %s", exc, exc_info=True)
        return []

    if resp.status_code == 401:
        # Token is invalid/expired; surface a clear error so higher-level code
        # can decide whether to refresh tokens.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="eBay Browse API token is invalid or expired",
        )

    if resp.status_code >= 500:
        logger.error(
            "Browse API server error status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        return []

    if resp.status_code != 200:
        logger.warning(
            "Browse API non-success status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        return []

    try:
        data = resp.json()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to parse Browse API response JSON: %s", exc, exc_info=True)
        return []

    summaries = data.get("itemSummaries") or []
    results: List[EbayListingSummary] = []

    for item in summaries:
        item_id = item.get("itemId") or item.get("legacyItemId")
        if not item_id:
            continue

        title = (item.get("title") or "").strip()

        price_obj = item.get("price") or {}
        try:
            price = float(price_obj.get("value") or 0.0)
        except (TypeError, ValueError):
            price = 0.0

        shipping_cost = 0.0
        shipping_obj = item.get("shippingOptions") or item.get("shippingCost")
        # Browse API may expose either a list of shippingOptions or a
        # single shippingCost object; we support both shapes.
        if isinstance(shipping_obj, list) and shipping_obj:
            cost_obj = shipping_obj[0].get("shippingCost") or {}
        elif isinstance(shipping_obj, dict):
            cost_obj = shipping_obj
        else:
            cost_obj = {}

        try:
            shipping_cost = float(cost_obj.get("value") or 0.0)
        except (TypeError, ValueError):
            shipping_cost = 0.0

        condition = item.get("condition") or item.get("conditionDisplayName")
        description = item.get("shortDescription") or None

        results.append(
            EbayListingSummary(
                item_id=str(item_id),
                title=title,
                price=price,
                shipping=shipping_cost,
                condition=condition,
                description=description,
            )
        )

    return results


async def place_buy_now_stub(ebay_item_id: str, amount: float) -> bool:
    """Stub for placing an immediate Buy It Now purchase on eBay.

    This is intentionally a no-op that only logs what would be done. A real
    implementation will replace this in a future phase.
    """

    logger.info("[auto-buy] BUY_NOW stub: item_id=%s amount=%.2f", ebay_item_id, amount)
    # Preserve async contract without performing any real I/O.
    await asyncio.sleep(0)
    return True


async def place_offer_stub(ebay_item_id: str, amount: float) -> bool:
    """Stub for placing a best offer on an eBay listing.

    As with place_buy_now_stub, this function only logs intent and always
    reports success for now.
    """

    logger.info("[auto-buy] OFFER stub: item_id=%s amount=%.2f", ebay_item_id, amount)
    await asyncio.sleep(0)
    return True
