from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import Inventory, InventoryStatus, SKU
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
    sku_id: int = Field(..., description="SKU.id of the catalog item")
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
    sku_id: int
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

    This endpoint is used by the LISTING UI: it accepts a batch of SKUs plus
    storage/status info and creates corresponding Inventory rows.
    """
    # Normalize global default status -> InventoryStatus
    default_status_enum = ALLOWED_LISTING_STATUS_MAP[payload.default_status]

    # Fetch all referenced SKUs in one query
    sku_ids = {item.sku_id for item in payload.items}
    sku_rows = db.query(SKU).filter(SKU.id.in_(sku_ids)).all()
    sku_by_id: Dict[int, SKU] = {s.id: s for s in sku_rows}

    missing = [sid for sid in sku_ids if sid not in sku_by_id]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "unknown_sku_ids", "ids": missing})

    # Optional: ensure all SKUs share the same model if model_id is provided
    if payload.model_id is not None:
        mismatched: Dict[int, str] = {}
        for sid, sku in sku_by_id.items():
            if sku.model and sku.model != str(payload.model_id) and sku.model != payload.model_id:
                mismatched[sid] = sku.model or ""
        if mismatched:
            logger.warning(
                "listing.commit model_id mismatch user=%s requested_model_id=%s mismatched=%s",
                current_user.id,
                payload.model_id,
                mismatched,
            )

    created_items: List[ListingCommitItemResponse] = []

    try:
        for item in payload.items:
            sku = sku_by_id[item.sku_id]

            # Resolve storage: per-row overrides global
            storage_value: Optional[str] = item.storage or payload.storage
            if not storage_value:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "missing_storage", "sku_id": item.sku_id},
                )

            # Resolve status
            status_key = (item.status or payload.default_status)
            status_enum = ALLOWED_LISTING_STATUS_MAP[status_key]

            inv = Inventory(
                sku_id=sku.id,
                sku_code=sku.sku_code,
                model=sku.model,
                category=sku.category,
                condition=sku.condition,
                part_number=sku.part_number,
                title=item.title or sku.title,
                price_value=item.price if item.price is not None else sku.price,
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
                    sku_id=sku.id,
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