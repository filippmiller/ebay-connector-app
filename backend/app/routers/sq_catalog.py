from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, asc, desc, func, select, text
from sqlalchemy.sql.sqltypes import String, Text, CHAR, VARCHAR, Unicode, UnicodeText, Integer, BigInteger, Numeric

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    SqItem,
    SqInternalCategory,
    SqShippingGroup,
    ItemCondition,
    Warehouse,
    tbl_parts_models_table,
    tbl_parts_category_table,
)
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from app.models.sq_item import (
    SqItemCreate,
    SqItemUpdate,
    SqItemRead,
    SqItemListItem,
    SqItemListResponse,
)


router = APIRouter(prefix="/api/sq", tags=["sq_catalog"])


@router.get("/models/search")
async def search_models(
    q: str = Query(..., min_length=1, description="Search term for legacy parts models table"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Live search endpoint for legacy ``tbl_parts_models`` table.

    Returns a compact list of ``{id, label}`` entries that can be used by the
    SKU create/edit form for model typeahead. The implementation is defensive
    and tolerates environments where the underlying table does not exist.
    """

    table = tbl_parts_models_table
    if table is None:
        return {"items": [], "total": 0}

    # Identify candidate ID and display label columns using simple heuristics
    string_types = (String, Text, CHAR, VARCHAR, Unicode, UnicodeText)
    numeric_types = (Integer, BigInteger, Numeric)

    columns = list(table.columns)
    if not columns:
        return {"items": [], "total": 0}

    id_col = None
    label_col = None

    for col in columns:
        if id_col is None and isinstance(col.type, numeric_types):
            id_col = col

        if isinstance(col.type, string_types):
            name_lower = col.name.lower()
            if any(key in name_lower for key in ("model", "name", "title", "part")):
                label_col = label_col or col

    if label_col is None:
        # Fallback: first text-like column
        for col in columns:
            if isinstance(col.type, string_types):
                label_col = col
                break

    if label_col is None:
        return {"items": [], "total": 0}

    if id_col is None:
        id_col = columns[0]

    # Use a contains search so that queries like "L500" match anywhere in the
    # model label. This is triggered explicitly from the UI (on Enter) so we
    # can afford a broader match.
    like = f"%{q}%"
    stmt = (
        select(id_col, label_col)
        .where(label_col.ilike(like))
        .order_by(label_col.asc())
        .limit(limit)
    )

    rows = db.execute(stmt).fetchall()
    items = [
        {"id": row[0], "label": str(row[1])}
        for row in rows
        if row[1] is not None
    ]

    return {"items": items, "total": len(items)}


@router.get("/items", response_model=SqItemListResponse)
async def list_sq_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sku: Optional[str] = Query(None),
    model_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    shipping_group: Optional[str] = Query(None),
    condition_id: Optional[int] = Query(None),
    has_alert: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Full-text search across SKU, title, description, part_number, MPN, UPC"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemListResponse:
    """Paginated list of SQ catalog items for the SKU grid.

    This endpoint is separate from the generic ``/api/grids`` infrastructure so
    the SKU tab and migration tools can rely on a stable, explicit contract.
    """

    query = db.query(SqItem)

    if sku:
        like = f"%{sku}%"
        query = query.filter(SqItem.sku.ilike(like))

    if model_id is not None:
        query = query.filter(SqItem.model_id == model_id)

    if category:
        query = query.filter(SqItem.category == category)

    if shipping_group:
        query = query.filter(SqItem.shipping_group == shipping_group)

    if condition_id is not None:
        query = query.filter(SqItem.condition_id == condition_id)

    if has_alert is True:
        query = query.filter(SqItem.alert_flag.is_(True))
    elif has_alert is False:
        query = query.filter(or_(SqItem.alert_flag.is_(False), SqItem.alert_flag.is_(None)))

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                SqItem.sku.ilike(like),
                SqItem.title.ilike(like),
                SqItem.description.ilike(like),
                SqItem.part_number.ilike(like),
                SqItem.mpn.ilike(like),
                SqItem.upc.ilike(like),
                SqItem.part.ilike(like),
            )
        )

    total = query.count()

    # Default sort: newest first by record_updated/record_created/id
    query = query.order_by(desc(SqItem.record_updated.nullslast()), desc(SqItem.record_created.nullslast()), desc(SqItem.id))

    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    items = [
        SqItemListItem.model_validate(
            {
                "id": r.id,
                "sku": r.sku,
                "model": r.model,
                "category": r.category,
                "condition_id": r.condition_id,
                "part_number": r.part_number,
                "price": r.price,
                "title": r.title,
                "brand": r.brand,
                "alert_flag": r.alert_flag,
                "shipping_group": r.shipping_group,
                "pic_url1": r.pic_url1,
                "record_created": r.record_created,
                "record_updated": r.record_updated,
                "record_status": r.record_status,
            }
        )
        for r in rows
    ]

    return SqItemListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/items/{item_id}", response_model=SqItemRead)
async def get_sq_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemRead:
    """Return full detail for a single SQ catalog item."""

    item = db.query(SqItem).filter(SqItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="SQ item not found")

    return SqItemRead.model_validate(item)


@router.post("/items", response_model=SqItemRead)
async def create_sq_item(
    payload: SqItemCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemRead:
    """Create a new SQ catalog item for the SKU popup form.

    The implementation mirrors the legacy semantics as closely as possible:

    * If ``sku`` is empty, the next numeric SKU is generated as ``MAX(SKU) + 1``.
    * ``Title`` is required and limited to 80 characters.
    * ``Price`` must be positive.
    * An internal category is required unless ``external_category_flag`` is set
      ("eBay category" mode).
    * Audit / status fields are initialised with sensible defaults.
    """

    now = datetime.now(timezone.utc)

    # --- High-level validation mirroring the UI rules ----------------------
    title = (payload.title or "").strip() if payload.title is not None else ""
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if len(title) > 80:
        raise HTTPException(status_code=400, detail="Title must be at most 80 characters")

    if payload.price is None or payload.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")

    # When not using external/eBay category, internal category is required.
    if not payload.external_category_flag:
        if payload.category is None or str(payload.category).strip() == "":
            raise HTTPException(status_code=400, detail="Internal category is required")

    data = payload.model_dump(exclude_unset=True)
    item = SqItem()
    for key, value in data.items():
        setattr(item, key, value)

    # --- Auto-generated numeric SKU ----------------------------------------
    if not item.sku:
        # ``SKU`` is stored as a numeric column on SKU_catalog. We still treat
        # it as a logical string in the API, but generation is purely numeric
        # using the legacy pattern MAX(SKU)+1.
        max_sku = db.query(func.max(SqItem.sku)).scalar()
        try:
            current_max = int(max_sku) if max_sku is not None else 0
        except (TypeError, ValueError):
            current_max = 0
        item.sku = current_max + 1
    else:
        # Ensure uniqueness when user provides an explicit SKU.
        existing = db.query(SqItem).filter(SqItem.sku == item.sku).first()
        if existing:
            raise HTTPException(status_code=400, detail="SKU must be unique")

    # --- Defaults mirroring legacy behaviour -------------------------------
    if not item.market:
        item.market = "eBay"

    # In the legacy system UseEbayID was stored as a text flag ("Y"/"N"). We
    # keep that contract even though the column is a plain Text field.
    if not item.use_ebay_id:
        item.use_ebay_id = "Y"

    # Record / status defaults
    if item.price is not None and item.price_updated is None:
        item.price_updated = now

    if item.record_status is None:
        item.record_status = 1
    if item.record_status_flag is None:
        item.record_status_flag = True
    if item.checked_status is None:
        item.checked_status = False

    # Audit fields
    username = (
        getattr(current_user, "username", None)
        or getattr(current_user, "email", None)
        or "system"
    )
    if not item.record_created:
        item.record_created = now
    item.record_created_by = username
    item.record_updated = now
    item.record_updated_by = username

    # Shipping / listing sensible defaults
    if not item.listing_type:
        item.listing_type = "FixedPriceItem"
    if not item.listing_duration:
        item.listing_duration = "GTC"
    if item.listing_duration_in_days is None:
        item.listing_duration_in_days = None

    db.add(item)
    db.commit()
    db.refresh(item)

    return SqItemRead.model_validate(item)


@router.put("/items/{item_id}", response_model=SqItemRead)
async def update_sq_item(
    item_id: int,
    payload: SqItemUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemRead:
    """Update an existing SQ catalog item.

    Only fields present in the payload are patched; audit fields are updated
    automatically. When the price changes, the previous value is moved to
    ``previous_price`` and ``price_updated`` is refreshed.
    """

    item = db.query(SqItem).filter(SqItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="SQ item not found")

    # Capture old price before patching
    old_price = item.price

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)

    now = datetime.now(timezone.utc)

    # If price changed and a new price was provided, update history fields.
    if "price" in data and item.price is not None and item.price != old_price:
        item.previous_price = old_price
        item.price_updated = now

    username = (
        getattr(current_user, "username", None)
        or getattr(current_user, "email", None)
        or "system"
    )
    item.record_updated = now
    item.record_updated_by = username

    db.commit()
    db.refresh(item)

    return SqItemRead.model_validate(item)


@router.get("/dictionaries")
async def get_sq_dictionaries(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Return dictionaries used by the SQ Create/Edit form.

    - Internal categories (sq_internal_categories)
    - Shipping groups (sq_shipping_groups)
    - Item conditions (item_conditions)
    - Warehouses (warehouses)
    - Static listing types / durations / sites
    """

    # Internal categories: prefer real legacy table tbl_parts_category when
    # available so that codes/labels match the old system exactly. Fallback
    # to sq_internal_categories otherwise.
    internal_categories: list[dict]
    try:
        # Use a direct SQL query so we are independent of SQLAlchemy reflection
        # quirks and column casing. We expect these three columns to exist in
        # the legacy table:
        #   CategoryID, CategoryDescr, ebayCategoryName
        rows = db.execute(
            text(
                'SELECT "CategoryID", "CategoryDescr", "ebayCategoryName" '
                'FROM tbl_parts_category ORDER BY "CategoryID"'
            )
        ).fetchall()

        if rows:
            internal_categories = []
            for cat_id, descr, ebay_name in rows:
                parts = [str(cat_id)]
                if descr:
                    parts.append(str(descr).strip())
                if ebay_name:
                    parts.append(str(ebay_name).strip())
                label = " — ".join(parts)
                internal_categories.append(
                    {"id": cat_id, "code": str(cat_id), "label": label}
                )
        else:
            raise ValueError("tbl_parts_category returned no rows")
    except Exception:
        # Fallback: use normalized sq_internal_categories dictionary.
        categories = (
            db.query(SqInternalCategory)
            .order_by(asc(SqInternalCategory.sort_order.nulls_last()), asc(SqInternalCategory.code))
            .all()
        )
        internal_categories = [
            {
                "id": c.id,
                "code": c.code,
                # Include code in the label so the dropdown still shows
                # code + description even in fallback mode.
                "label": f"{c.code} — {c.label}",
            }
            for c in categories
        ]

    shipping_groups = (
        db.query(SqShippingGroup)
        .order_by(asc(SqShippingGroup.sort_order.nulls_last()), asc(SqShippingGroup.code))
        .all()
    )
    conditions = (
        db.query(ItemCondition)
        .order_by(asc(ItemCondition.sort_order.nulls_last()), asc(ItemCondition.code))
        .all()
    )
    warehouses = db.query(Warehouse).order_by(asc(Warehouse.id)).all()

    listing_types = [
        {"code": "FixedPriceItem", "label": "Fixed price"},
        {"code": "Auction", "label": "Auction"},
    ]

    listing_durations = [
        {"code": "GTC", "label": "Good 'Til Cancelled", "days": None},
        {"code": "30", "label": "30 days", "days": 30},
        {"code": "7", "label": "7 days", "days": 7},
    ]

    sites = [
        {"code": "EBAY-US", "label": "eBay US", "site_id": 0},
    ]

    return {
        "internal_categories": internal_categories,
        "shipping_groups": [
            {"id": g.id, "code": g.code, "label": g.label}
            for g in shipping_groups
        ],
        "conditions": [
            {"id": cond.id, "code": cond.code, "label": cond.label}
            for cond in conditions
        ],
        "warehouses": [
            {"id": w.id, "name": w.name, "location": w.location, "warehouse_type": w.warehouse_type}
            for w in warehouses
        ],
        "listing_types": listing_types,
        "listing_durations": listing_durations,
        "sites": sites,
    }
