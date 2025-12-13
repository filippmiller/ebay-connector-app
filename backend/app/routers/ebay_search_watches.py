from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbaySearchWatch
from app.models.user import User as UserModel
from app.services.auth import get_current_active_user
from app.services.ebay import ebay_service
from app.services.ebay_api_client import search_active_listings

from app.utils.logger import logger


router = APIRouter(prefix="/api/ebay/search-watches", tags=["ebay_search_watches"])


class EbaySearchWatchBase(BaseModel):
    name: str = Field(..., description="Human-readable name of the rule")
    keywords: str = Field(..., description="Search keywords, e.g. 'MacBook Pro 2020'")
    max_total_price: Optional[float] = Field(
        None,
        description="Optional maximum total price (item + shipping) in listing currency",
    )
    category_hint: Optional[str] = Field(
        "laptop",
        description="Optional type hint: 'laptop', 'all', etc.",
    )
    exclude_keywords: Optional[List[str]] = Field(
        None,
        description="Case-insensitive words that must NOT appear in title/description (e.g. parts)",
    )
    check_interval_sec: Optional[int] = Field(
        60,
        ge=10,
        le=3600,
        description="Minimal interval between checks for this rule in seconds",
    )
    enabled: bool = Field(True, description="Whether the watch is active")
    notification_mode: str = Field(
        "task",
        description="Notification mode: 'task' (Task + TaskNotification) or 'none'",
    )


class EbaySearchWatchCreate(EbaySearchWatchBase):
    pass


class EbaySearchWatchUpdate(BaseModel):
    name: Optional[str] = None
    keywords: Optional[str] = None
    max_total_price: Optional[float] = None
    category_hint: Optional[str] = None
    exclude_keywords: Optional[List[str]] = None
    check_interval_sec: Optional[int] = Field(None, ge=10, le=3600)
    enabled: Optional[bool] = None
    notification_mode: Optional[str] = None


class EbaySearchWatchResponse(EbaySearchWatchBase):
    id: str
    last_checked_at: Optional[datetime]

    class Config:
        orm_mode = True


class RunOnceListing(BaseModel):
    item_id: str
    title: str
    price: float
    shipping: float
    total_price: float
    condition: Optional[str]
    description: Optional[str]
    ebay_url: Optional[str]


def _ensure_owner(watch: EbaySearchWatch, current_user: UserModel) -> None:
    if watch.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this watch rule",
        )


def _normalize_exclude_keywords(raw: Optional[List[str]]) -> List[str]:
    if not raw:
        return []
    result: List[str] = []
    for w in raw:
        s = (w or "").strip()
        if s:
            result.append(s)
    return result


@router.get("", response_model=List[EbaySearchWatchResponse])
async def list_watches(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[EbaySearchWatchResponse]:
    rows: List[EbaySearchWatch] = (
        db.query(EbaySearchWatch)
        .filter(EbaySearchWatch.user_id == current_user.id)
        .order_by(EbaySearchWatch.created_at.desc())
        .all()
    )
    return rows


@router.post("", response_model=EbaySearchWatchResponse, status_code=status.HTTP_201_CREATED)
async def create_watch(
    payload: EbaySearchWatchCreate,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EbaySearchWatchResponse:
    data = payload.dict()
    data["exclude_keywords"] = _normalize_exclude_keywords(data.get("exclude_keywords"))

    watch = EbaySearchWatch(
        user_id=current_user.id,
        name=data["name"].strip(),
        keywords=data["keywords"].strip(),
        max_total_price=data.get("max_total_price"),
        category_hint=(data.get("category_hint") or "").strip() or None,
        exclude_keywords=data.get("exclude_keywords") or None,
        check_interval_sec=data.get("check_interval_sec") or 60,
        enabled=data.get("enabled", True),
        notification_mode=(data.get("notification_mode") or "task").strip() or "task",
    )

    db.add(watch)
    db.commit()
    db.refresh(watch)

    logger.info("[watch] created ebay_search_watch id=%s user_id=%s", watch.id, current_user.id)
    return watch


@router.patch("/{watch_id}", response_model=EbaySearchWatchResponse)
async def update_watch(
    watch_id: str,
    payload: EbaySearchWatchUpdate,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EbaySearchWatchResponse:
    watch: Optional[EbaySearchWatch] = db.query(EbaySearchWatch).filter(EbaySearchWatch.id == watch_id).one_or_none()
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch rule not found")

    _ensure_owner(watch, current_user)

    data = payload.dict(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        watch.name = data["name"].strip()
    if "keywords" in data and data["keywords"] is not None:
        watch.keywords = data["keywords"].strip()
    if "max_total_price" in data:
        watch.max_total_price = data["max_total_price"]
    if "category_hint" in data:
        ch = data["category_hint"]
        watch.category_hint = ch.strip() if ch is not None else None
    if "exclude_keywords" in data:
        watch.exclude_keywords = _normalize_exclude_keywords(data.get("exclude_keywords")) or None
    if "check_interval_sec" in data and data["check_interval_sec"] is not None:
        watch.check_interval_sec = int(data["check_interval_sec"])
    if "enabled" in data and data["enabled"] is not None:
        watch.enabled = bool(data["enabled"])
    if "notification_mode" in data and data["notification_mode"] is not None:
        nm = (data["notification_mode"] or "").strip() or "task"
        watch.notification_mode = nm

    db.commit()
    db.refresh(watch)

    logger.info("[watch] updated ebay_search_watch id=%s user_id=%s", watch.id, current_user.id)
    return watch


@router.delete("/{watch_id}", status_code=status.HTTP_200_OK)
async def delete_watch(
    watch_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    watch: Optional[EbaySearchWatch] = db.query(EbaySearchWatch).filter(EbaySearchWatch.id == watch_id).one_or_none()
    if not watch:
        # Idempotent delete
        return {"deleted": 0}

    _ensure_owner(watch, current_user)

    db.delete(watch)
    db.commit()

    logger.info("[watch] deleted ebay_search_watch id=%s user_id=%s", watch.id, current_user.id)
    return {"deleted": 1}


@router.post("/{watch_id}/run-once", response_model=List[RunOnceListing])
async def run_watch_once(
    watch_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[RunOnceListing]:
    """Execute a single Browse search for an existing watch rule.

    This does not create any tasks/notifications; it is intended for UI preview
    and diagnostics.
    """

    watch: Optional[EbaySearchWatch] = db.query(EbaySearchWatch).filter(EbaySearchWatch.id == watch_id).one_or_none()
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch rule not found")

    _ensure_owner(watch, current_user)

    keywords = (watch.keywords or "").strip()
    if not keywords:
        return []

    access_token = await ebay_service.get_browse_app_token()

    listings = await search_active_listings(access_token, keywords, limit=50)

    # Apply the same filters as the main browse endpoint (duplicated here to
    # keep the router independent of UI-layer models).
    max_total = float(watch.max_total_price or 0) if watch.max_total_price is not None else None
    category_hint = (watch.category_hint or "").strip() or None
    exclude = [
        (w or "").strip().lower()
        for w in (watch.exclude_keywords or [])
        if (w or "").strip()
    ]

    def _accept(summary) -> bool:
        total_price = float((summary.price or 0.0) + (summary.shipping or 0.0))
        if max_total is not None and total_price > max_total:
            return False

        title = (summary.title or "").lower()
        desc = (summary.description or "").lower()

        if category_hint and category_hint.lower() == "laptop":
            laptop_tokens = ["laptop", "notebook", "ноутбук"]
            if not (any(t in title for t in laptop_tokens) or any(t in desc for t in laptop_tokens)):
                return False

        for bad in exclude:
            if bad in title or bad in desc:
                return False

        return True

    results: List[RunOnceListing] = []
    for s in listings:
        if not _accept(s):
            continue
        total_price = float((s.price or 0.0) + (s.shipping or 0.0))
        results.append(
            RunOnceListing(
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
