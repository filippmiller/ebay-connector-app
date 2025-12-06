"""Lightweight eBay Browse/Search API client used by the monitoring worker.

This module intentionally keeps the surface area small: it exposes a single
function to search active listings by keyword using an OAuth access token
obtained elsewhere (EbayToken or application token).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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


@dataclass
class TaxonomyCategorySuggestion:
    """Lightweight representation of a Taxonomy category suggestion."""

    id: str
    name: str
    path: str


async def search_active_listings(
    access_token: str,
    keywords: str,
    *,
    limit: int = 20,
    offset: int = 0,
    sort: str = "newlyListed",
    category_id: Optional[str] = None,
    filter_expr: Optional[str] = None,
    fieldgroups: Optional[List[str]] = None,
    aspect_filter: Optional[str] = None,
    return_raw: bool = False,
):
    """Search active listings for the given keywords via the Browse API.

    This function uses the Buy Browse API `item_summary/search` endpoint.
    It is intentionally conservative: on any HTTP or parsing error it logs
    and returns an empty list so the monitoring worker can continue.

    When ``return_raw`` is True, the function returns a tuple of
    (listings, raw_json); otherwise it returns just the listings list for
    backwards compatibility with existing callers.
    """

    keywords = (keywords or "").strip()
    if not access_token or not keywords:
        return ([], {}) if return_raw else []

    base = settings.ebay_api_base_url.rstrip("/")
    url = f"{base}/buy/browse/v1/item_summary/search"

    # Map internal sort keys to eBay API sort keys if needed.
    # For now we pass through, but we handle the price/newlyListed mapping in the caller or here.
    # eBay API values: price, -price, newlyListed, etc.

    params = {
        "q": keywords,
        # Limit the number of results per model to avoid flooding candidates.
        "limit": str(max(1, min(limit, 200))),  # Increased max limit to 200
        "offset": str(offset),
        "sort": sort,
    }
    if category_id:
        params["category_ids"] = category_id
    if filter_expr:
        params["filter"] = filter_expr
    if fieldgroups:
        params["fieldgroups"] = ",".join(fieldgroups)
    if aspect_filter:
        params["aspect_filter"] = aspect_filter

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
        return ([], {}) if return_raw else []

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
        return ([], {}) if return_raw else []

    if resp.status_code != 200:
        logger.warning(
            "Browse API non-success status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        return ([], {}) if return_raw else []

    try:
        data = resp.json()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to parse Browse API response JSON: %s", exc, exc_info=True)
        return ([], {}) if return_raw else []

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

    if return_raw:
        return results, data

    return results


async def get_category_suggestions(
    access_token: str,
    keywords: str,
    *,
    limit: int = 5,
) -> List[TaxonomyCategorySuggestion]:
    """Return Taxonomy category suggestions for the given keywords.

    This wraps the Commerce Taxonomy `get_category_suggestions` endpoint for the
    default EBAY_US category tree (tree id 0).
    """

    keywords = (keywords or "").strip()
    if not access_token or not keywords:
        return []

    base = settings.ebay_api_base_url.rstrip("/")
    # For EBAY_US the default category tree id is 0.
    url = f"{base}/commerce/taxonomy/v1/category_tree/0/get_category_suggestions"

    params = {
        "q": keywords,
        "limit": str(max(1, min(limit, 20))),
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = await client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:  # pragma: no cover - network dependent
        logger.error(
            "Taxonomy get_category_suggestions request error: %s", exc, exc_info=True
        )
        return []

    if resp.status_code != 200:
        logger.warning(
            "Taxonomy get_category_suggestions non-success status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        return []

    try:
        data: Dict[str, Any] = resp.json()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Failed to parse Taxonomy get_category_suggestions JSON: %s",
            exc,
            exc_info=True,
        )
        return []

    raw_suggestions = data.get("categorySuggestions") or []
    suggestions: List[TaxonomyCategorySuggestion] = []

    for s in raw_suggestions:
        category = s.get("category") or {}
        cat_id = category.get("categoryId")
        cat_name = category.get("categoryName")
        if not cat_id or not cat_name:
            continue

        ancestors = s.get("categoryTreeNodeAncestors") or []
        parts = [a.get("categoryName") for a in ancestors if a.get("categoryName")]
        parts.append(cat_name)
        path = " > ".join(parts)

        suggestions.append(
            TaxonomyCategorySuggestion(
                id=str(cat_id),
                name=str(cat_name),
                path=path,
            )
        )

    return suggestions


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
