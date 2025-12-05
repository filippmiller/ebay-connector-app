from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.models.user import User as UserModel
from app.services.auth import get_current_active_user
from app.services.ebay import ebay_service
from app.services.ebay_api_client import EbayListingSummary, search_active_listings


router = APIRouter(prefix="/api/ebay/browse", tags=["ebay_browse"])


class BrowseSearchRequest(BaseModel):
    keywords: str = Field(..., description="Search keywords, e.g. 'Lenovo L500'")
    max_total_price: Optional[float] = Field(
        None,
        description="Optional maximum total price (item + shipping) in listing currency",
    )
    category_hint: Optional[str] = Field(
        "laptop",
        description="Optional type hint: e.g. 'laptop' to prefer whole laptops, or 'all' to disable.",
    )
    exclude_keywords: Optional[List[str]] = Field(
        None,
        description="Case-insensitive words that must NOT appear in title or description (e.g. parts)",
    )
    limit: int = Field(50, ge=1, le=200, description="Max number of listings to fetch from Browse API")
    offset: int = Field(0, ge=0, description="Number of items to skip (pagination)")
    sort: Optional[str] = Field("newlyListed", description="Sort order: price, -price, newlyListed")


class BrowseListing(BaseModel):
    item_id: str
    title: str
    price: float
    shipping: float
    total_price: float
    condition: Optional[str]
    description: Optional[str]
    ebay_url: Optional[str]


def _matches_category_hint(summary: EbayListingSummary, category_hint: Optional[str]) -> bool:
    """Heuristic category filter based on title/description.

    For the initial version we avoid calling extra Browse fields and instead
    rely on keywords in the title/description. This can be refined later.
    """

    if not category_hint or category_hint.lower() in {"all", "any"}:
        return True

    title = (summary.title or "").lower()
    desc = (summary.description or "" ).lower()

    if category_hint.lower() == "laptop":
        laptop_tokens = ["laptop", "notebook", "ноутбук"]
        if any(t in title for t in laptop_tokens) or any(t in desc for t in laptop_tokens):
            return True
        return False

    # Unknown hint – fall back to no extra filtering
    return True


def _matches_exclude_keywords(summary: EbayListingSummary, exclude_keywords: Optional[List[str]]) -> bool:
    if not exclude_keywords:
        return True

    title = (summary.title or "").lower()
    desc = (summary.description or "" ).lower()

    for bad in exclude_keywords:
        b = (bad or "").strip().lower()
        if not b:
            continue
        if b in title or b in desc:
            return False
    return True


@router.post("/search", response_model=List[BrowseListing])
async def search_ebay_browse(
    payload: BrowseSearchRequest,
    current_user: UserModel = Depends(get_current_active_user),  # noqa: ARG001
) -> List[BrowseListing]:
    """Search active eBay listings via Browse API and apply simple filters.

    This endpoint is a thin wrapper over the internal Browse API client used by
    workers. It lets the UI perform on-demand searches using the same logic
    that monitoring/AI workers rely on.
    """

    keywords = (payload.keywords or "").strip()
    if not keywords:
        return []

    # Use shared application Browse token – read-only scope, cached in memory.
    access_token = await ebay_service.get_browse_app_token()

    summaries = await search_active_listings(
        access_token,
        keywords,
        limit=payload.limit,
        offset=payload.offset,
        sort=payload.sort or "newlyListed",
    )

    results: List[BrowseListing] = []

    for s in summaries:
        # Basic price + shipping filter
        total_price = float((s.price or 0.0) + (s.shipping or 0.0))
        if payload.max_total_price is not None and total_price > payload.max_total_price:
            continue

        # Category/type hint (e.g. restrict to whole laptops)
        if not _matches_category_hint(s, payload.category_hint):
            continue

        # Exclude parts/undesired keywords
        if not _matches_exclude_keywords(s, payload.exclude_keywords):
            continue

        results.append(
            BrowseListing(
                item_id=s.item_id,
                title=s.title,
                price=float(s.price or 0.0),
                shipping=float(s.shipping or 0.0),
                total_price=total_price,
                condition=s.condition,
                description=s.description,
                ebay_url=f"https://www.ebay.com/itm/{s.item_id}",
            )
        )

    return results
