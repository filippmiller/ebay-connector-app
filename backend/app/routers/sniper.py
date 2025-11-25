from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbayAccount, EbaySnipe, EbaySnipeStatus, EbayToken
from app.models.user import User as UserModel
from app.services.auth import get_current_user


router = APIRouter(prefix="/api/sniper", tags=["sniper"])


class SnipeCreate(BaseModel):
    ebay_account_id: str = Field(..., description="ID of ebay_accounts row that owns this snipe")
    item_id: str = Field(..., description="eBay Item ID for the auction")
    max_bid_amount: float = Field(..., gt=0, description="Maximum bid amount the sniper may place")
    seconds_before_end: int = Field(
        5,
        ge=0,
        le=600,
        description="How many seconds before auction end we should bid",
    )
    comment: Optional[str] = Field(
        None,
        description="Optional free-form note describing the intent/context of the snipe",
    )


class SnipeUpdate(BaseModel):
    """Editable fields for an existing snipe.

    Only timing (seconds_before_end), max bid amount, comment and a transition
    to CANCELLED are allowed while the snipe is still mutable. Core identity
    fields (ebay_account_id, item_id, end_time) are immutable once created.
    """

    max_bid_amount: Optional[float] = Field(None, gt=0)
    seconds_before_end: Optional[int] = Field(None, ge=0, le=600)
    comment: Optional[str] = None

    # Status update (e.g. cancel)
    status: Optional[EbaySnipeStatus] = None


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _snipe_to_row(s: EbaySnipe) -> Dict[str, Any]:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "ebay_account_id": s.ebay_account_id,
        "item_id": s.item_id,
        "title": s.title,
        "image_url": s.image_url,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "fire_at": s.fire_at.isoformat() if getattr(s, "fire_at", None) else None,
        "max_bid_amount": _decimal_to_float(s.max_bid_amount),
        "currency": s.currency,
        "seconds_before_end": s.seconds_before_end,
        "status": s.status,
        "current_bid_at_creation": _decimal_to_float(s.current_bid_at_creation),
        "result_price": _decimal_to_float(s.result_price),
        "result_message": s.result_message,
        "comment": getattr(s, "comment", None),
        "contingency_group_id": s.contingency_group_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _ensure_account_access(
    db: Session, current_user: UserModel, ebay_account_id: Optional[str]
) -> None:
    """Best-effort access control for ebay_account_id.

    We follow the existing pattern used in shipping and other routers: scope
    access to accounts whose org_id matches the current user.id. If the
    account is missing or belongs to a different org, we reject the request.
    """

    if not ebay_account_id:
        return

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == ebay_account_id)
        .one_or_none()
    )
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="eBay account not found",
        )
    if getattr(account, "org_id", None) not in (None, current_user.id):
        # org_id may be null for some accounts; in that case we allow access.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this eBay account",
        )


@router.get("/snipes")
async def list_snipes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Optional status or comma-separated list of statuses"),
    ebay_account_id: Optional[str] = None,
    search: Optional[str] = Query(
        None, description="Search by item id or title (case-insensitive)"
    ),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """List sniper entries for the current user.

    Response shape matches other grid-style endpoints used by DataGridPage.
    """

    q = db.query(EbaySnipe).outerjoin(
        EbayAccount, EbaySnipe.ebay_account_id == EbayAccount.id
    )

    # Scope to the current user / org.
    q = q.filter(EbaySnipe.user_id == current_user.id)

    if status:
        raw_statuses = [s.strip() for s in status.split(",") if s.strip()]
        if raw_statuses:
            q = q.filter(EbaySnipe.status.in_(raw_statuses))

    if ebay_account_id:
        _ensure_account_access(db, current_user, ebay_account_id)
        q = q.filter(EbaySnipe.ebay_account_id == ebay_account_id)

    if search:
        like = f"%{search}%"
        q = q.filter(
            (EbaySnipe.item_id.ilike(like)) | (EbaySnipe.title.ilike(like))
        )

    total = q.count()
    q = q.order_by(desc(EbaySnipe.created_at))
    rows: List[EbaySnipe] = q.offset(offset).limit(limit).all()

    return {
        "rows": [_snipe_to_row(s) for s in rows],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


def _compute_fire_at(end_time: datetime, seconds_before_end: int) -> datetime:
    """Compute fire_at timestamp from end_time and seconds_before_end.

    The result is always normalized to UTC and never later than end_time.
    """

    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    else:
        end_time = end_time.astimezone(timezone.utc)
    secs = max(0, int(seconds_before_end))
    # We do not bake in any additional safety margin here; workers can add
    # their own internal safeguards if needed.
    return end_time - timedelta(seconds=secs)


async def _fetch_auction_metadata(
    db: Session, ebay_account_id: str, item_id: str
) -> Dict[str, Any]:
    """Fetch auction metadata from eBay Browse API for the given account and item.

    This helper:
    - loads the latest EbayToken row for the account;
    - calls Buy Browse get_item_by_legacy_id with that token;
    - validates that the listing exists, is an auction and not yet ended;
    - returns a small dict with end_time, title, currency, current_price,
      and image_url.

    NOTE: This is a v1 implementation and focuses on the core fields needed by
    Sniper. It is intentionally defensive and will surface clear 4xx errors
    when the item is not suitable for sniping.
    """

    token_row: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == ebay_account_id)
        .order_by(EbayToken.updated_at.desc())
        .first()
    )
    if not token_row or not getattr(token_row, "access_token", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active eBay token found for this account. Please reconnect the account.",
        )

    access_token = token_row.access_token  # type: ignore[attr-defined]

    base_url = settings.ebay_api_base_url.rstrip("/")
    url = f"{base_url}/buy/browse/v1/item/get_item_by_legacy_id"
    params = {"legacy_item_id": item_id}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to contact eBay Browse API: {exc}",
        )

    if resp.status_code != 200:
        # Best-effort extraction of error message without leaking tokens.
        try:
            body = resp.json()
        except Exception:
            body = {"message": resp.text[:500]}
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Failed to fetch item details from eBay", "status": resp.status_code, "body": body},
        )

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid JSON returned from eBay Browse API",
        )

    # Validate auction vs fixed-price listing.
    buying_options = data.get("buyingOptions") or []
    is_auction = False
    if isinstance(buying_options, list):
        for opt in buying_options:
            if isinstance(opt, str) and "AUCTION" in opt.upper():
                is_auction = True
                break
    if not is_auction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The specified item is not an auction listing.",
        )

    # Parse end time.
    raw_end = data.get("itemEndDate") or data.get("itemEndDateUtc")
    if not raw_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay did not return an end time for this item.",
        )
    try:
        end_time = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to parse auction end time from eBay response: {raw_end}",
        )
    if end_time <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auction already ended; cannot schedule a new snipe.",
        )

    title = data.get("title")

    # Price and currency.
    price_info = data.get("price") or {}
    currency = "USD"
    current_price: Optional[float] = None
    if isinstance(price_info, dict):
        currency = price_info.get("currency") or currency
        value = price_info.get("value")
        try:
            current_price = float(value) if value is not None else None
        except (TypeError, ValueError):
            current_price = None

    # Image URL: prefer image.imageUrl, fall back to images[0].imageUrl.
    image_url: Optional[str] = None
    image_obj = data.get("image")
    if isinstance(image_obj, dict):
        image_url = image_obj.get("imageUrl")
    if not image_url:
        images = data.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                image_url = first.get("imageUrl")

    return {
        "end_time": end_time,
        "title": title,
        "currency": currency,
        "current_price": current_price,
        "image_url": image_url,
    }


def _compute_fire_at(end_time: datetime, seconds_before_end: int) -> datetime:
    """Return a UTC fire_at timestamp derived from end_time and seconds_before_end."""

    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    else:
        end_time = end_time.astimezone(timezone.utc)
    secs = max(0, int(seconds_before_end))
    # We do not bake in any additional safety margin here; workers can add
    # their own internal safeguards if needed.
    return end_time - timedelta(seconds=secs)


@router.post("/snipes", status_code=status.HTTP_201_CREATED)
async def create_snipe(
    payload: SnipeCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create a new sniper entry.

    In v2 the client only provides minimal fields (account, item_id, max bid,
    optional seconds_before_end and comment). All auction metadata is fetched
    from eBay on the server side and stored with the snipe.
    """

    _ensure_account_access(db, current_user, payload.ebay_account_id)

    meta = await _fetch_auction_metadata(db, payload.ebay_account_id, payload.item_id)
    end_time: datetime = meta["end_time"]
    seconds_before_end = payload.seconds_before_end or 5
    fire_at = _compute_fire_at(end_time, seconds_before_end)

    now = datetime.now(timezone.utc)

    snipe = EbaySnipe(
        user_id=current_user.id,
        ebay_account_id=payload.ebay_account_id,
        item_id=payload.item_id,
        title=meta.get("title"),
        image_url=meta.get("image_url"),
        end_time=end_time,
        fire_at=fire_at,
        max_bid_amount=payload.max_bid_amount,
        currency=(meta.get("currency") or "USD").upper(),
        seconds_before_end=seconds_before_end,
        status=EbaySnipeStatus.scheduled.value,
        current_bid_at_creation=meta.get("current_price"),
        comment=payload.comment,
        created_at=now,
        updated_at=now,
    )

    db.add(snipe)
    db.commit()
    db.refresh(snipe)

    return _snipe_to_row(snipe)


@router.patch("/snipes/{snipe_id}")
async def update_snipe(
    snipe_id: str,
    payload: SnipeUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update editable fields of a snipe or cancel it.

    Only snipes in PENDING or SCHEDULED state are mutable. Terminal states
    (executed_stub, won, lost, error, cancelled) are read-only.
    """

    snipe: Optional[EbaySnipe] = (
        db.query(EbaySnipe)
        .filter(EbaySnipe.id == snipe_id, EbaySnipe.user_id == current_user.id)
        .one_or_none()
    )
    if not snipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snipe not found")

    current_status = EbaySnipeStatus(snipe.status)
    mutable_states = {EbaySnipeStatus.pending, EbaySnipeStatus.scheduled}

    # Status transition handling
    if payload.status is not None and payload.status != current_status:
        # Only allow transitions to CANCELLED for mutable states, or between
        # PENDING and SCHEDULED.
        if current_status not in mutable_states:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change status of snipe in state {current_status.value}",
            )

        if payload.status == EbaySnipeStatus.cancelled:
            snipe.status = EbaySnipeStatus.cancelled.value
        elif {
            current_status,
            payload.status,
        } <= mutable_states:  # allow pending<->scheduled
            snipe.status = payload.status.value
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported status transition",
            )

    # Field updates only allowed for mutable states
    if current_status in mutable_states:
        if payload.max_bid_amount is not None:
            snipe.max_bid_amount = payload.max_bid_amount
        if payload.seconds_before_end is not None:
            snipe.seconds_before_end = payload.seconds_before_end
            snipe.fire_at = _compute_fire_at(snipe.end_time, snipe.seconds_before_end)
        if payload.comment is not None:
            snipe.comment = payload.comment
    else:
        # Client attempted to change fields of an immutable snipe.
        immutable_change = any(
            [
                payload.max_bid_amount is not None,
                payload.seconds_before_end is not None,
                payload.comment is not None,
            ]
        )
        if immutable_change:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot modify snipe fields when status is {current_status.value}",
            )

    snipe.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(snipe)

    return _snipe_to_row(snipe)


@router.delete("/snipes/{snipe_id}")
async def delete_snipe(
    snipe_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Logically cancel a snipe.

    Instead of hard-deleting rows, we mark them as CANCELLED so history is
    preserved in the grid. Only pending/scheduled snipes can be cancelled.
    """

    snipe: Optional[EbaySnipe] = (
        db.query(EbaySnipe)
        .filter(EbaySnipe.id == snipe_id, EbaySnipe.user_id == current_user.id)
        .one_or_none()
    )
    if not snipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snipe not found")

    current_status = EbaySnipeStatus(snipe.status)
    if current_status not in {EbaySnipeStatus.pending, EbaySnipeStatus.scheduled}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel snipe in state {current_status.value}",
        )

    snipe.status = EbaySnipeStatus.cancelled.value
    snipe.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(snipe)

    return _snipe_to_row(snipe)
