from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.models.user import User as UserModel
from app.services.auth import get_current_active_user
from app.services.ebay import ebay_service
from app.services.ebay_api_client import (
    EbayListingSummary,
    TaxonomyCategorySuggestion,
    get_category_suggestions,
    search_active_listings,
)
from app.utils.logger import logger


router = APIRouter(prefix="/api/ebay/browse", tags=["ebay_browse"])


class BrowseSearchRequest(BaseModel):
    keywords: str = Field(..., description="Search keywords, e.g. 'Lenovo L500'")
    max_total_price: Optional[float] = Field(
        None,
        description="Optional maximum total price (item + shipping) in listing currency",
    )
    min_total_price: Optional[float] = Field(
        None,
        description="Optional minimum total price (item + shipping) in listing currency",
    )
    category_id: Optional[str] = Field(
        None,
        description="Optional eBay categoryId to bias search results and refinements.",
    )
    category_hint: Optional[str] = Field(
        "laptop",
        description="Optional type hint: e.g. 'laptop' to prefer whole laptops, or 'all' to disable.",
    )
    exclude_keywords: Optional[List[str]] = Field(
        None,
        description="Case-insensitive words that must NOT appear in title or description (e.g. parts)",
    )
    condition_ids: Optional[List[str]] = Field(
        None,
        description="Optional list of eBay conditionIds to include (Browse filter conditionIds).",
    )
    aspect_filters: Optional[Dict[str, List[str]]] = Field(
        None,
        description="Optional map of aspectName -> list of values for Browse aspect_filter.",
    )
    limit: int = Field(50, ge=1, le=200, description="Max number of listings to fetch from Browse API")
    offset: int = Field(0, ge=0, description="Number of items to skip (pagination)")
    sort: Optional[str] = Field("newlyListed", description="Sort order: price, -price, newlyListed")
    include_refinements: bool = Field(
        True,
        description=(
            "If true, also return category/aspect/condition refinements from the Browse API "
            "so the UI can render ebay.com-style sidebars."
        ),
    )
    use_taxonomy_suggestions: bool = Field(
        True,
        description=(
            "If true and no category_id is provided, call Taxonomy get_category_suggestions "
            "to pick likely categories and optionally scope Browse to the best match."
        ),
    )


class BrowseListing(BaseModel):
    item_id: str
    title: str
    price: float
    shipping: float
    total_price: float
    condition: Optional[str]
    description: Optional[str]
    ebay_url: Optional[str]
    # New fields for card display
    image_url: Optional[str] = None
    seller_name: Optional[str] = None
    seller_location: Optional[str] = None
    item_condition: Optional[str] = None


class CategoryRefinement(BaseModel):
    id: str
    name: str
    match_count: int


class AspectValueRefinement(BaseModel):
    value: str
    match_count: int


class AspectRefinement(BaseModel):
    name: str
    values: List[AspectValueRefinement]


class ConditionRefinement(BaseModel):
    id: str
    name: str
    match_count: int


class TaxonomySuggestion(BaseModel):
    id: str
    name: str
    path: str


class BrowseSearchResponse(BaseModel):
    items: List[BrowseListing]
    categories: List[CategoryRefinement] = []
    aspects: List[AspectRefinement] = []
    conditions: List[ConditionRefinement] = []
    taxonomy_suggestions: List[TaxonomySuggestion] = []
    total: Optional[int] = None


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


@router.post("/search", response_model=BrowseSearchResponse)
async def search_ebay_browse(
    payload: BrowseSearchRequest,
    current_user: UserModel = Depends(get_current_active_user),  # noqa: ARG001
) -> BrowseSearchResponse:
    """Search active eBay listings via Browse API and apply simple filters.

    This endpoint is a thin wrapper over the internal Browse API client used by
    workers. It lets the UI perform on-demand searches using the same logic
    that monitoring/AI workers rely on. In addition to normalized listings it
    also exposes category/aspect/condition refinements so the UI can render
    sidebars similar to ebay.com.
    """

    keywords = (payload.keywords or "").strip()
    if not keywords:
        return BrowseSearchResponse(items=[])

    # Use shared application Browse token – read-only scope, cached in memory.
    access_token = await ebay_service.get_browse_app_token()

    # Optionally use Taxonomy suggestions to infer a likely category tree.
    resolved_category_id = payload.category_id
    taxonomy_suggestions_models: List[TaxonomySuggestion] = []
    if payload.use_taxonomy_suggestions and not resolved_category_id:
        try:
            tx_suggestions: List[TaxonomyCategorySuggestion] = await get_category_suggestions(
                access_token, keywords, limit=5
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Taxonomy category suggestions failed: %s", exc, exc_info=True)
            tx_suggestions = []

        for s in tx_suggestions:
            taxonomy_suggestions_models.append(
                TaxonomySuggestion(id=s.id, name=s.name, path=s.path)
            )

        if tx_suggestions:
            # Use the best suggestion to scope the initial Browse query.
            resolved_category_id = tx_suggestions[0].id

    # Build Browse API filter expression for basic numeric filters.
    filters: List[str] = []
    if payload.min_total_price is not None or payload.max_total_price is not None:
        lo = payload.min_total_price if payload.min_total_price is not None else 0
        hi = payload.max_total_price if payload.max_total_price is not None else ""
        filters.append(f"price:[{lo}..{hi}]")

    # Condition filter using conditionIds from UI/refinements.
    if payload.condition_ids:
        condition_ids = [str(cid) for cid in payload.condition_ids if cid]
        if condition_ids:
            filters.append(f"conditionIds:{{{','.join(condition_ids)}}}")

    filter_expr = ",".join(filters) if filters else None

    # Aspect filter: Screen Size, Processor, OS, Brand etc.
    aspect_filter_param: Optional[str] = None
    if payload.aspect_filters:
        parts: List[str] = []
        for name, values in payload.aspect_filters.items():
            clean_values = [v for v in values if v]
            if not clean_values:
                continue
            parts.append(f"{name}:{{{'|'.join(clean_values)}}}")
        if parts:
            aspect_filter_param = ",".join(parts)

    fieldgroups: List[str] = ["MATCHING_ITEMS"]
    if payload.include_refinements:
        fieldgroups.extend([
            "CATEGORY_REFINEMENTS",
            "ASPECT_REFINEMENTS",
            "CONDITION_REFINEMENTS",
        ])

    summaries, raw = await search_active_listings(
        access_token,
        keywords,
        limit=payload.limit,
        offset=payload.offset,
        sort=payload.sort or "newlyListed",
        category_id=resolved_category_id,
        filter_expr=filter_expr,
        fieldgroups=fieldgroups,
        aspect_filter=aspect_filter_param,
        return_raw=True,
    )

    results: List[BrowseListing] = []

    for s in summaries:
        # Basic price + shipping filter on total (item + shipping)
        total_price = float((s.price or 0.0) + (s.shipping or 0.0))
        if payload.max_total_price is not None and total_price > payload.max_total_price:
            continue
        if payload.min_total_price is not None and total_price < payload.min_total_price:
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
                # New fields for card display
                image_url=s.image_url,
                seller_name=s.seller_name,
                seller_location=s.seller_location,
                item_condition=s.condition,
            )
        )

    # Map refinements into a compact, UI-friendly structure.
    refinement = (raw or {}).get("refinement") or {}

    categories: List[CategoryRefinement] = []
    for c in refinement.get("categoryDistributions") or []:
        cat_id = c.get("categoryId")
        name = c.get("categoryName")
        if not cat_id or not name:
            continue
        categories.append(
            CategoryRefinement(
                id=str(cat_id),
                name=str(name),
                match_count=int(c.get("matchCount") or 0),
            )
        )

    aspects: List[AspectRefinement] = []
    for a in refinement.get("aspectDistributions") or []:
        aspect_name = a.get("localizedAspectName") or a.get("aspectName")
        if not aspect_name:
            continue
        values: List[AspectValueRefinement] = []
        for v in a.get("aspectValueDistributions") or []:
            val = v.get("localizedValue") or v.get("value")
            if not val:
                continue
            values.append(
                AspectValueRefinement(
                    value=str(val),
                    match_count=int(v.get("matchCount") or 0),
                )
            )
        if values:
            aspects.append(AspectRefinement(name=str(aspect_name), values=values))

    conditions: List[ConditionRefinement] = []
    for c in refinement.get("conditionDistributions") or []:
        cond_id = c.get("conditionId")
        name = c.get("condition")
        if not cond_id or not name:
            continue
        conditions.append(
            ConditionRefinement(
                id=str(cond_id),
                name=str(name),
                match_count=int(c.get("matchCount") or 0),
            )
        )

    total = raw.get("total") if isinstance(raw, dict) else None

    return BrowseSearchResponse(
        items=results,
        categories=categories,
        aspects=aspects,
        conditions=conditions,
        taxonomy_suggestions=taxonomy_suggestions_models,
        total=total,
    )
