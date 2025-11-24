from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from sqlalchemy.sql.sqltypes import (
    String,
    Text,
    CHAR,
    VARCHAR,
    Unicode,
    UnicodeText,
    Integer,
    BigInteger,
    Numeric,
    Float,
    Boolean as SA_Boolean,
    DateTime as SA_DateTime,
    Date as SA_Date,
)

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import Inventory, InventoryStatus, SqItem, SKU, TblPartsInventory
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


from datetime import datetime


def _get_or_create_simple_sku(db: Session, sq: SqItem) -> int:
    """Return ID from simplified SKU table for a given SqItem.

    The Supabase `inventory` table uses a foreign key to the modern `sku`
    table (SKU model). Historically we tried to leave `sku_id` NULL when
    committing listings directly from the legacy SQ catalog, but the real
    production schema has a NOT NULL constraint on `inventory.sku_id`.

    To keep referential integrity without changing the DB schema, we lazily
    create a minimal `SKU` row for any SqItem that does not yet have a
    corresponding simplified SKU entry, keyed by the numeric SKU value.
    """
    from decimal import Decimal

    if sq.sku is None:
        raise HTTPException(status_code=400, detail={"error": "sq_item_missing_sku", "id": sq.id})

    try:
        sku_code_str = str(int(sq.sku))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error": "sq_item_invalid_sku", "id": sq.id, "sku": str(sq.sku)})

    existing = db.query(SKU).filter(SKU.sku_code == sku_code_str).first()
    if existing:
        return existing.id

    # Derive a minimal but useful simplified SKU from the SQ catalog row.
    price_val: float = 0.0
    if sq.price is not None:
        if isinstance(sq.price, Decimal):
            price_val = float(sq.price)
        else:
            try:
                price_val = float(sq.price)
            except Exception:
                price_val = 0.0

    category_str = None
    if sq.category is not None:
        try:
            category_str = str(int(sq.category))
        except Exception:
            category_str = str(sq.category)

    simple_sku = SKU(
        sku_code=sku_code_str,
        model=None,
        category=category_str,
        condition=None,
        part_number=sq.part_number,
        price=price_val,
        title=sq.part,
        description=sq.description,
        brand=getattr(sq, "brand", None),
        image_url=sq.pic_url1,
    )

    db.add(simple_sku)
    db.flush()  # assign ID
    return simple_sku.id


def _insert_legacy_inventory_row(
    db: Session,
    sq: SqItem,
    storage_value: str,
    status_key: str,
    username: str,
    next_id: int,
    item_payload: DraftListingItemPayload,
) -> int:
    """Insert a row into legacy tbl_parts_inventory with explicit ID.

    ID is computed outside as MAX(ID)+1, then incremented per-row within the
    same commit batch so that new rows appear at the end of tbl_parts_inventory
    exactly as in the legacy flow.
    """

    table = TblPartsInventory.__table__

    insert_data: Dict[str, Any] = {"ID": next_id}

    # Case-insensitive column lookup
    cols_by_lower = {c.name.lower(): c for c in table.columns}

    # SKU
    sku_val = None
    if sq.sku is not None:
        try:
            sku_val = int(sq.sku)
        except Exception:
            try:
                sku_val = int(str(sq.sku))
            except Exception:
                sku_val = None
    if sku_val is not None:
        for key in ["sku", "skucode", "overstocksku"]:
            col = cols_by_lower.get(key)
            if col is not None:
                insert_data[col.name] = sku_val
                break

    # Quantity
    qty = item_payload.quantity or 1
    for key in ["quantity", "qty", "overstockqty"]:
        col = cols_by_lower.get(key)
        if col is not None:
            insert_data[col.name] = qty
            break

    # Storage ID
    for key in [
        "storageid",
        "storage_id",
        "storage",
        "alternativestorage",
        "alternative_storage",
        "storagealias",
        "storage_alias",
    ]:
        col = cols_by_lower.get(key)
        if col is not None:
            insert_data[col.name] = storage_value
            break

    # Title / overview title
    title_val = (item_payload.title or sq.part or sq.description or "").strip()
    if title_val:
        for key in ["overviewtitle", "title", "part", "itemtitle"]:
            col = cols_by_lower.get(key)
            if col is not None:
                insert_data[col.name] = title_val
                break

    # Description
    desc_val = (sq.description or "").strip()
    if desc_val:
        for key in ["overviewdescription", "description", "overdescription", "overdescription1"]:
            col = cols_by_lower.get(key)
            if col is not None:
                insert_data[col.name] = desc_val
                break

    # Category
    if sq.category is not None:
        try:
            cat_val: Any = int(sq.category)
        except Exception:
            cat_val = sq.category
        for key in ["categoryid", "category", "overstockcategoryid"]:
            col = cols_by_lower.get(key)
            if col is not None:
                insert_data[col.name] = cat_val
                break

    # Price
    price_val = None
    if item_payload.price is not None:
        price_val = float(item_payload.price)
    elif sq.price is not None:
        try:
            price_val = float(sq.price)
        except Exception:
            price_val = None
    if price_val is not None:
        for key in ["price", "overstockprice", "buyprice"]:
            col = cols_by_lower.get(key)
            if col is not None:
                insert_data[col.name] = price_val
                break

    # Author
    for key in ["author", "user", "overstockuser"]:
        col = cols_by_lower.get(key)
        if col is not None:
            insert_data[col.name] = username
            break

    # Rec created
    now = datetime.utcnow()
    for key in ["reccreated", "record_created", "created", "overstockcreated"]:
        col = cols_by_lower.get(key)
        if col is not None:
            insert_data[col.name] = now
            break

    # Fill NOT NULL columns without defaults with safe placeholders
    string_types = (String, Text, CHAR, VARCHAR, Unicode, UnicodeText)

    for col in table.columns:
        if col.name in insert_data:
            continue
        if col.nullable:
            continue
        if col.default is not None or col.server_default is not None:
            continue

        t = col.type
        if isinstance(t, (Integer, BigInteger, Numeric, Float)):
            insert_data[col.name] = 0
        elif isinstance(t, string_types):
            insert_data[col.name] = ""
        elif isinstance(t, SA_Boolean):
            insert_data[col.name] = False
        elif isinstance(t, SA_DateTime):
            insert_data[col.name] = now
        elif isinstance(t, SA_Date):
            insert_data[col.name] = now.date()
        else:
            insert_data[col.name] = None

    stmt = table.insert().values(**insert_data)
    db.execute(stmt)
    return next_id


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
    # SqItem.sku is stored as a NUMERIC column, but the API contract exposes
    # sku_code as a string. Normalise everything to a canonical string key
    # based on the integer SKU value so lookups are robust.
    normalised_codes: Dict[str, str] = {}
    for item in payload.items:
        try:
            key = str(int(item.sku_code))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_sku_code", "sku_code": item.sku_code},
            )
        normalised_codes[key] = item.sku_code

    sq_rows = db.query(SqItem).filter(SqItem.sku.in_([int(k) for k in normalised_codes.keys()])).all()

    sq_by_code: Dict[str, SqItem] = {}
    for s in sq_rows:
        if s.sku is None:
            continue
        try:
            key = str(int(s.sku))
        except (TypeError, ValueError):
            continue
        sq_by_code[key] = s

    missing = [orig for key, orig in normalised_codes.items() if key not in sq_by_code]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "unknown_sku_codes", "codes": missing})

    created_items: List[ListingCommitItemResponse] = []

    try:
        # Compute starting legacy inventory ID once (MAX(ID)+1)
        legacy_table = TblPartsInventory.__table__
        try:
            max_id = db.query(func.max(legacy_table.c.ID)).scalar()
        except Exception:
            max_id = None
        next_legacy_id = int(max_id or 0) + 1

        for item in payload.items:
            key = str(int(item.sku_code))
            sq = sq_by_code[key]

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

            # Map SQ catalog row → inventory logical fields.
            # Ensure we always have a valid inventory.sku_id by resolving or
            # creating a corresponding simplified SKU row.
            inv = Inventory(
                sku_id=_get_or_create_simple_sku(db, sq),
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

            # Also mirror into legacy tbl_parts_inventory
            _insert_legacy_inventory_row(
                db=db,
                sq=sq,
                storage_value=storage_value,
                status_key=status_key,
                username=current_user.username,
                next_id=next_legacy_id,
                item_payload=item,
            )
            next_legacy_id += 1

            created_items.append(
                ListingCommitItemResponse(
                    inventory_id=inv.id,
                    sku_code=str(int(sq.sku)) if sq.sku is not None else "",
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