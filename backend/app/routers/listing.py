from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import Inventory, InventoryStatus, SqItem
from app.services.auth import get_current_user
from app.models.user import User
from app.utils.logger import logger

router = APIRouter(prefix="/api/listing", tags=["listing"])


ALLOWED_LISTING_STATUS_MAP: Dict[str, InventoryStatus] = {
    # UI label -> InventoryStatus mapping
    "awaiting_moderation": InventoryStatus.PENDING_LISTING,
    "checked": InventoryStatus.AVAILABLE,
}


class DraftListingItemPayload(BaseModel):
    sku_code: str = Field(..., description="SqItem.sku from the SQ catalog (sq_items) table")
    price: Optional[float] = Field(None)
    quantity: int = Field(1, ge=1)
    condition: Optional[str] = None
    title: Optional[str] = None
    storage: Optional[str] = None
    status: Optional[str] = Field(None, description="UI status code (awaiting_moderation|checked)")
    warehouse_id: Optional[int] = None

    @validator("status")
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v_norm = v.strip().lower()
        if v_norm not in ALLOWED_LISTING_STATUS_MAP:
            raise ValueError("Invalid status; allowed: awaiting_moderation, checked")
        return v_norm

    @validator("sku_code")
    def validate_sku_code(cls, v: str) -> str:
        v_norm = (v or "").strip()
        if not v_norm:
            raise ValueError("sku_code is required")
        return v_norm


class ListingCommitRequest(BaseModel):
    model_id: Optional[int] = Field(None, description="Optional model id to enforce consistency")
    storage: Optional[str] = Field(None, description="Global storage fallback (e.g. B16:1)")
    default_status: Optional[str] = Field("awaiting_moderation")
    items: List[DraftListingItemPayload]

    @validator("items")
    def validate_items_non_empty(cls, v: List[DraftListingItemPayload]) -> List[DraftListingItemPayload]:
        if not v:
            raise ValueError("items must be non-empty")
        return v

    @validator("default_status", pre=True, always=True)
    def validate_default_status(cls, v: Optional[str]) -> str:
        if not v:
            return "awaiting_moderation"
        v_norm = v.strip().lower()
        if v_norm not in ALLOWED_LISTING_STATUS_MAP:
            raise ValueError("Invalid default_status; allowed: awaiting_moderation, checked")
        return v_norm


class ListingCommitItemResponse(BaseModel):
    inventory_id: int
    sku_code: str
    storage: Optional[str]
    status: str


class ListingCommitResponse(BaseModel):
    created_count: int
    items: List[ListingCommitItemResponse]


@router.post("/commit", response_model=ListingCommitResponse)
async def commit_listing_items(
    payload: ListingCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ListingCommitResponse:
    """Commit draft listing items into the inventory table.

    This endpoint is used by the LISTING UI: it accepts a batch of draft rows
    keyed by SQ catalog SKU (SqItem.sku) and creates corresponding Inventory
    rows in Supabase using the `sq_items` (SQ catalog) table.
    """
    # Normalize global default status -> InventoryStatus (also validates value)
    _ = ALLOWED_LISTING_STATUS_MAP[payload.default_status]

    # Fetch all referenced SQ catalog rows in one query using sku (logical sku_code).
    sku_codes = {item.sku_code for item in payload.items}
    sq_rows = db.query(SqItem).filter(SqItem.sku.in_(sku_codes)).all()
    sq_by_code: Dict[str, SqItem] = {s.sku: s for s in sq_rows if s.sku}

    missing = [code for code in sku_codes if code not in sq_by_code]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "unknown_sku_codes", "codes": missing})

    created_items: List[ListingCommitItemResponse] = []

    try:
        for item in payload.items:
            sq = sq_by_code[item.sku_code]

            # Resolve storage: per-row overrides global
            storage_value: Optional[str] = item.storage or payload.storage
            if not storage_value:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "missing_storage", "sku_code": item.sku_code},
                )

            # Resolve status
            status_key = (item.status or payload.default_status)
            status_enum = ALLOWED_LISTING_STATUS_MAP[status_key]

            # Map SQ catalog row  inventory logical fields.
            # Note: Inventory.sku_id points to the simplified SKU table and is
            # left NULL here because we are sourcing from sq_items instead.
            inv = Inventory(
                sku_id=None,
                sku_code=sq.sku,
                model=sq.model,
                category=sq.category,
                condition=None,
                part_number=sq.part_number,
                title=item.title or sq.title or sq.part,
                price_value=item.price if item.price is not None else (float(sq.price) if sq.price is not None else None),
                price_currency=None,
                status=status_enum,
                photo_count=0,
                storage_id=storage_value,
                storage=storage_value,
                warehouse_id=item.warehouse_id,
                quantity=item.quantity,
                author=current_user.username,
            )

            db.add(inv)
            db.flush()  # assign ID

            created_items.append(
                ListingCommitItemResponse(
                    inventory_id=inv.id,
                    sku_code=sq.sku,
                    storage=inv.storage,
                    status=inv.status.value if inv.status else "",
                )
            )

        db.commit()
    except HTTPException:
        # Re-raise user errors without wrapping
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("listing.commit failed user=%s error=%s", current_user.id, str(e))
        raise HTTPException(status_code=400, detail={"error": "commit_failed", "message": str(e)})

    return ListingCommitResponse(created_count=len(created_items), items=created_items)