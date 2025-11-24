from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbayAccount, EbaySnipe, EbaySnipeStatus
from app.models.user import User as UserModel
from app.services.auth import get_current_user


router = APIRouter(prefix="/api/sniper", tags=["sniper"])


class SnipeCreate(BaseModel):
    ebay_account_id: Optional[str] = Field(
        None, description="ID of ebay_accounts row that owns this snipe"
    )
    item_id: str = Field(..., description="eBay Item ID for the auction")
    title: Optional[str] = Field(
        None, description="Optional human-readable title cached at creation time"
    )
    image_url: Optional[str] = Field(
        None, description="Optional image URL cached at creation time"
    )
    end_time: datetime = Field(
        ..., description="Auction end time (UTC). In the future this will be fetched from eBay."
    )
    max_bid_amount: float = Field(..., gt=0, description="Maximum bid amount the sniper may place")
    currency: str = Field("USD", min_length=3, max_length=3)
    seconds_before_end: int = Field(
        5,
        ge=0,
        le=600,
        description="How many seconds before auction end we should bid",
    )
    contingency_group_id: Optional[str] = Field(
        None,
        description="Optional logical group id for future advanced strategies (one-of-many etc.)",
    )

    @validator("end_time", pre=True)
    def _parse_end_time(cls, v: Any) -> datetime:  # type: ignore[override]
        # Pydantic will already parse most ISO strings; here we only ensure tz-aware UTC.
        dt = v
        if not isinstance(dt, datetime):
            dt = datetime.fromisoformat(str(v))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt


class SnipeUpdate(BaseModel):
    # Editable while snipe is still pending/scheduled
    max_bid_amount: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    seconds_before_end: Optional[int] = Field(None, ge=0, le=600)
    end_time: Optional[datetime] = None
    title: Optional[str] = None
    image_url: Optional[str] = None
    contingency_group_id: Optional[str] = None

    # Status update (e.g. cancel)
    status: Optional[EbaySnipeStatus] = None

    @validator("end_time", pre=True)
    def _parse_end_time_optional(cls, v: Any) -> Optional[datetime]:  # type: ignore[override]
        if v is None:
            return None
        dt = v
        if not isinstance(dt, datetime):
            dt = datetime.fromisoformat(str(v))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt


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
        "max_bid_amount": _decimal_to_float(s.max_bid_amount),
        "currency": s.currency,
        "seconds_before_end": s.seconds_before_end,
        "status": s.status,
        "current_bid_at_creation": _decimal_to_float(s.current_bid_at_creation),
        "result_price": _decimal_to_float(s.result_price),
        "result_message": s.result_message,
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
    status: Optional[EbaySnipeStatus] = Query(None),
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

    if status is not None:
        q = q.filter(EbaySnipe.status == status.value)

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


@router.post("/snipes", status_code=status.HTTP_201_CREATED)
async def create_snipe(
    payload: SnipeCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create a new sniper entry.

    For now we *require* the client to send end_time. A future iteration may
    look up the auction details from eBay based on item_id.
    """

    _ensure_account_access(db, current_user, payload.ebay_account_id)

    # Normalize end_time to UTC (validator already does this, but keep for clarity).
    end_time = payload.end_time
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    else:
        end_time = end_time.astimezone(timezone.utc)

    now = datetime.now(timezone.utc)

    snipe = EbaySnipe(
        user_id=current_user.id,
        ebay_account_id=payload.ebay_account_id,
        item_id=payload.item_id,
        title=payload.title,
        image_url=payload.image_url,
        end_time=end_time,
        max_bid_amount=payload.max_bid_amount,
        currency=payload.currency.upper(),
        seconds_before_end=payload.seconds_before_end,
        status=EbaySnipeStatus.pending.value,
        contingency_group_id=payload.contingency_group_id,
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
        if payload.currency is not None:
            snipe.currency = payload.currency.upper()
        if payload.seconds_before_end is not None:
            snipe.seconds_before_end = payload.seconds_before_end
        if payload.end_time is not None:
            end_time = payload.end_time
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            else:
                end_time = end_time.astimezone(timezone.utc)
            snipe.end_time = end_time
        if payload.title is not None:
            snipe.title = payload.title
        if payload.image_url is not None:
            snipe.image_url = payload.image_url
        if payload.contingency_group_id is not None:
            snipe.contingency_group_id = payload.contingency_group_id
    else:
        # Client attempted to change fields of an immutable snipe.
        immutable_change = any(
            [
                payload.max_bid_amount is not None,
                payload.currency is not None,
                payload.seconds_before_end is not None,
                payload.end_time is not None,
                payload.title is not None,
                payload.image_url is not None,
                payload.contingency_group_id is not None,
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
