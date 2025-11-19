from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, asc, desc

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    SqItem,
    SqInternalCategory,
    SqShippingGroup,
    ItemCondition,
    Warehouse,
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
    """Create a new SQ catalog item.

    ``record_created`` / ``record_created_by`` are populated automatically.
    """

    now = datetime.now(timezone.utc)

    data = payload.model_dump(exclude_unset=True)
    item = SqItem()
    for key, value in data.items():
        setattr(item, key, value)

    # Auto-generate SKU if not provided – simple prefix + timestamp for now
    if not item.sku:
        item.sku = f"SQ-{int(now.timestamp())}"

    if not item.record_created:
        item.record_created = now
    item.record_created_by = current_user.username if getattr(current_user, "username", None) else (current_user.email if getattr(current_user, "email", None) else "system")

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
    automatically.
    """

    item = db.query(SqItem).filter(SqItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="SQ item not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)

    now = datetime.now(timezone.utc)
    item.record_updated = now
    item.record_updated_by = current_user.username if getattr(current_user, "username", None) else (current_user.email if getattr(current_user, "email", None) else "system")

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

    categories = (
        db.query(SqInternalCategory)
        .order_by(asc(SqInternalCategory.sort_order.nulls_last()), asc(SqInternalCategory.code))
        .all()
    )
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
        "internal_categories": [
            {"id": c.id, "code": c.code, "label": c.label}
            for c in categories
        ],
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
