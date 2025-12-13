from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, and_, func
from typing import Optional, List
from datetime import datetime
import csv
import io

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import (
    Inventory,
    InventoryStatus,
    EbayStatus,
    ConditionType,
    Warehouse,
    PartsDetail,
    PartsDetailStatus,
)
from ..services.auth import get_current_user, admin_required
from ..models.user import User
from ..utils.logger import logger

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/search")
async def search_inventory(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ebay_status: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    storage: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    sku_code: Optional[str] = Query(None),
    item_id: Optional[str] = Query(None),
    ebay_listing_id: Optional[str] = Query(None),
    part_number: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    tracking_number: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort: str = Query("rec_created", regex="^(rec_created|price_value|sku_code|title|status|ebay_status)$"),
    dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Comprehensive inventory search with multi-filter support.
    Optimized for production use with indexed queries.
    """
    query = db.query(Inventory)
    
    if q:
        search_term = f"%{q}%"
        query = query.filter(
            or_(
                Inventory.sku_code.ilike(search_term),
                Inventory.title.ilike(search_term),
                Inventory.part_number.ilike(search_term),
                Inventory.model.ilike(search_term)
            )
        )
    
    if status:
        statuses = [s.strip().upper() for s in status.split(',')]
        valid_statuses = []
        for s in statuses:
            try:
                valid_statuses.append(InventoryStatus[s])
            except KeyError:
                pass
        if valid_statuses:
            query = query.filter(Inventory.status.in_(valid_statuses))
    
    if ebay_status:
        ebay_statuses = [s.strip().upper() for s in ebay_status.split(',')]
        valid_ebay_statuses = []
        for s in ebay_statuses:
            try:
                valid_ebay_statuses.append(EbayStatus[s])
            except KeyError:
                pass
        if valid_ebay_statuses:
            query = query.filter(Inventory.ebay_status.in_(valid_ebay_statuses))
    
    if condition:
        conditions = [c.strip().upper() for c in condition.split(',')]
        valid_conditions = []
        for c in conditions:
            try:
                valid_conditions.append(ConditionType[c])
            except KeyError:
                pass
        if valid_conditions:
            query = query.filter(Inventory.condition.in_(valid_conditions))
    
    if category:
        categories = [c.strip() for c in category.split(',')]
        query = query.filter(Inventory.category.in_(categories))
    
    if storage:
        query = query.filter(Inventory.storage_id.ilike(f"{storage}%"))
    
    if warehouse_id:
        try:
            query = query.filter(Inventory.warehouse_id == int(warehouse_id))
        except:
            pass
    
    if sku_code:
        query = query.filter(Inventory.sku_code.ilike(f"%{sku_code}%"))
    
    if item_id or ebay_listing_id:
        search_id = item_id or ebay_listing_id
        query = query.filter(Inventory.ebay_listing_id.ilike(f"%{search_id}%"))
    
    if part_number:
        query = query.filter(Inventory.part_number.ilike(f"%{part_number}%"))
    
    if author:
        query = query.filter(Inventory.author.ilike(f"%{author}%"))
    
    if tracking_number:
        query = query.filter(Inventory.tracking_number.ilike(f"%{tracking_number}%"))
    
    if date_from:
        try:
            from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            query = query.filter(Inventory.rec_created >= from_dt)
        except:
            pass
    
    if date_to:
        try:
            to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            query = query.filter(Inventory.rec_created <= to_dt)
        except:
            pass
    
    total = query.count()
    
    order_col = getattr(Inventory, sort)
    if dir == "desc":
        query = query.order_by(desc(order_col))
    else:
        query = query.order_by(asc(order_col))
    
    rows = query.offset(offset).limit(limit).all()
    
    return {
        "rows": [
            {
                "id": r.id,
                "sku_code": r.sku_code,
                "model": r.model,
                "category": r.category,
                "condition": r.condition.value if r.condition else None,
                "part_number": r.part_number,
                "title": r.title,
                "price_value": float(r.price_value) if r.price_value else None,
                "price_currency": r.price_currency,
                "ebay_listing_id": r.ebay_listing_id,
                "ebay_status": r.ebay_status.value if r.ebay_status else None,
                "status": r.status.value if r.status else "AVAILABLE",
                "photo_count": r.photo_count or 0,
                "storage_id": r.storage_id,
                "storage": r.storage,
                "warehouse_id": r.warehouse_id,
                "quantity": r.quantity,
                "rec_created": r.rec_created.isoformat() if r.rec_created else None,
                "rec_updated": r.rec_updated.isoformat() if r.rec_updated else None,
                "author": r.author,
                "buyer_info": r.buyer_info,
                "tracking_number": r.tracking_number,
                "notes": r.notes,
                "parts_detail_id": r.parts_detail_id,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/filters")
async def get_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get distinct filter values for UI dropdowns"""
    categories = db.query(Inventory.category).distinct().filter(Inventory.category.isnot(None)).all()
    warehouses = db.query(Warehouse.id, Warehouse.code, Warehouse.name).all()
    storage_prefixes = db.query(
        func.substring(Inventory.storage_id, 1, 3).label('prefix')
    ).distinct().filter(Inventory.storage_id.isnot(None)).limit(50).all()
    
    return {
        "statuses": [s.value for s in InventoryStatus],
        "ebay_statuses": [s.value for s in EbayStatus],
        "conditions": [c.value for c in ConditionType],
        "categories": [c[0] for c in categories if c[0]],
        "warehouses": [{"id": w.id, "code": w.code, "name": w.name} for w in warehouses],
        "storage_prefixes": [p[0] for p in storage_prefixes if p[0]]
    }


@router.get("/{id}")
async def get_inventory_item(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get single inventory item with full details"""
    item = db.query(Inventory).filter(Inventory.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    
    warehouse = db.query(Warehouse).filter(Warehouse.id == item.warehouse_id).first() if item.warehouse_id else None
    
    return {
        "id": item.id,
        "sku_id": item.sku_id,
        "sku_code": item.sku_code,
        "model": item.model,
        "category": item.category,
        "condition": item.condition.value if item.condition else None,
        "part_number": item.part_number,
        "title": item.title,
        "price_value": float(item.price_value) if item.price_value else None,
        "price_currency": item.price_currency,
        "ebay_listing_id": item.ebay_listing_id,
        "ebay_status": item.ebay_status.value if item.ebay_status else None,
        "status": item.status.value if item.status else "AVAILABLE",
        "photo_count": item.photo_count or 0,
        "storage_id": item.storage_id,
        "storage": item.storage,
        "warehouse_id": item.warehouse_id,
        "warehouse": {"id": warehouse.id, "code": warehouse.code, "name": warehouse.name} if warehouse else None,
        "quantity": item.quantity,
        "rec_created": item.rec_created.isoformat() if item.rec_created else None,
        "rec_updated": item.rec_updated.isoformat() if item.rec_updated else None,
        "author": item.author,
        "buyer_info": item.buyer_info,
        "tracking_number": item.tracking_number,
        "notes": item.notes,
        "raw_payload": item.raw_payload,
        "parts_detail_id": item.parts_detail_id,
    }


@router.patch("/{id}")
async def update_inventory_item(
    id: int,
    status: Optional[str] = None,
    storage_id: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    price_value: Optional[float] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Partial update for inline edits (admin only).

    When a row is linked to parts_detail via parts_detail_id, status changes
    are mirrored to PartsDetail.status_sku so that the eBay listing worker
    sees consistent lifecycle states.
    """
    item = db.query(Inventory).filter(Inventory.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    old_status = item.status

    if status:
        try:
            item.status = InventoryStatus[status.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid status")
    
    if storage_id is not None:
        item.storage_id = storage_id
        item.storage = storage_id
    
    if warehouse_id is not None:
        warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not warehouse:
            raise HTTPException(status_code=400, detail="Invalid warehouse")
        item.warehouse_id = warehouse_id
    
    if price_value is not None:
        item.price_value = price_value
    
    if notes is not None:
        item.notes = notes

    # Keep PartsDetail.status_sku in sync when an Inventory row is linked and
    # its high-level status changes. We intentionally only handle the core
    # states used by the listing worker.
    if item.parts_detail_id is not None and old_status != item.status:
        pd = db.query(PartsDetail).filter(PartsDetail.id == item.parts_detail_id).one_or_none()
        if pd is not None:
            if item.status == InventoryStatus.PENDING_LISTING:
                pd.status_sku = PartsDetailStatus.AWAITING_MODERATION.value
            elif item.status == InventoryStatus.AVAILABLE:
                pd.status_sku = PartsDetailStatus.CHECKED.value
            elif item.status == InventoryStatus.LISTED:
                pd.status_sku = PartsDetailStatus.LISTED_ACTIVE.value

            pd.status_updated_at = datetime.utcnow()
            pd.status_updated_by = current_user.username
    
    item.rec_updated = datetime.utcnow()
    db.commit()
    db.refresh(item)
    
    return {"success": True, "id": item.id}


@router.post("/admin/bulk")
async def bulk_action(
    ids: List[int],
    action: str,
    payload: Optional[dict] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Bulk actions on inventory items.
    Actions: freeze, relist, mark_listed, mark_group_listed, cancel_listings, change_listings
    """
    updated = []
    failed = []
    
    for item_id in ids:
        try:
            item = db.query(Inventory).filter(Inventory.id == item_id).first()
            if not item:
                failed.append({"id": item_id, "reason": "Item not found"})
                continue
            
            if action == "freeze":
                item.status = InventoryStatus.FROZEN
            elif action == "relist":
                item.status = InventoryStatus.PENDING_LISTING
            elif action == "mark_listed":
                item.status = InventoryStatus.LISTED
                if payload and "ebay_listing_id" in payload:
                    item.ebay_listing_id = payload["ebay_listing_id"]
                item.ebay_status = EbayStatus.ACTIVE
            elif action == "mark_group_listed":
                item.status = InventoryStatus.LISTED
                item.ebay_status = EbayStatus.ACTIVE
            elif action == "cancel_listings":
                item.ebay_status = EbayStatus.ENDED
                item.status = InventoryStatus.AVAILABLE
            elif action == "change_listings":
                if payload and "price_value" in payload:
                    item.price_value = payload["price_value"]
            else:
                failed.append({"id": item_id, "reason": f"Unknown action: {action}"})
                continue
            
            item.rec_updated = datetime.utcnow()
            updated.append(item_id)
            
        except Exception as e:
            failed.append({"id": item_id, "reason": str(e)})
    
    db.commit()
    
    return {
        "updated": len(updated),
        "failed": failed
    }


@router.get("/export.csv")
async def export_inventory_csv(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ebay_status: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    storage: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export inventory with filters to CSV"""
    query = db.query(Inventory)
    
    if q:
        search_term = f"%{q}%"
        query = query.filter(
            or_(
                Inventory.sku_code.ilike(search_term),
                Inventory.title.ilike(search_term),
                Inventory.part_number.ilike(search_term)
            )
        )
    
    if status:
        statuses = [InventoryStatus[s.strip().upper()] for s in status.split(',') if s.strip().upper() in InventoryStatus.__members__]
        if statuses:
            query = query.filter(Inventory.status.in_(statuses))
    
    rows = query.order_by(desc(Inventory.rec_created)).limit(10000).all()
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'id', 'sku_code', 'model', 'category', 'condition', 'part_number', 'title',
        'price_value', 'price_currency', 'ebay_listing_id', 'ebay_status', 'status',
        'photo_count', 'storage_id', 'warehouse_id', 'quantity', 'rec_created', 'author'
    ])
    writer.writeheader()
    
    for r in rows:
        writer.writerow({
            'id': r.id,
            'sku_code': r.sku_code or '',
            'model': r.model or '',
            'category': r.category or '',
            'condition': r.condition.value if r.condition else '',
            'part_number': r.part_number or '',
            'title': r.title or '',
            'price_value': float(r.price_value) if r.price_value else '',
            'price_currency': r.price_currency or '',
            'ebay_listing_id': r.ebay_listing_id or '',
            'ebay_status': r.ebay_status.value if r.ebay_status else '',
            'status': r.status.value if r.status else '',
            'photo_count': r.photo_count or 0,
            'storage_id': r.storage_id or '',
            'warehouse_id': r.warehouse_id or '',
            'quantity': r.quantity or 1,
            'rec_created': r.rec_created.isoformat() if r.rec_created else '',
            'author': r.author or ''
        })
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inventory_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
    )
