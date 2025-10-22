from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import Optional
from datetime import datetime

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import Inventory, InventoryStatus, SKU
from ..services.auth import get_current_user, admin_required
from ..models.user import User

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("")
async def get_inventory(
    status: Optional[str] = Query(None),
    warehouse: Optional[int] = Query(None),
    sku: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("rec_created", regex="^(rec_created|sku_code|status|cost)$"),
    dir: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get inventory with filtering and pagination"""
    query = db.query(Inventory)
    
    if status:
        try:
            inv_status = InventoryStatus[status.upper()]
            query = query.filter(Inventory.status == inv_status)
        except KeyError:
            pass
    if warehouse:
        query = query.filter(Inventory.warehouse_id == warehouse)
    if sku:
        query = query.filter(Inventory.sku_code.ilike(f"%{sku}%"))
    if q:
        query = query.filter(
            (Inventory.sku_code.ilike(f"%{q}%")) |
            (Inventory.title.ilike(f"%{q}%"))
        )
    
    total_count = query.count()
    
    order_col = getattr(Inventory, sort)
    if dir == "desc":
        query = query.order_by(desc(order_col))
    else:
        query = query.order_by(asc(order_col))
    
    items = query.offset(offset).limit(limit).all()
    
    return {
        "items": [
            {
                "id": item.id,
                "sku_code": item.sku_code,
                "title": item.title,
                "status": item.status.value if item.status else "AVAILABLE",
                "storage": item.storage,
                "warehouse_id": item.warehouse_id,
                "cost": float(item.cost) if item.cost else 0,
                "expected_price": float(item.expected_price) if item.expected_price else 0,
                "category": item.category,
                "condition": item.condition,
                "image_url": item.image_url,
                "notes": item.notes,
                "quantity": item.quantity,
            }
            for item in items
        ],
        "total": total_count,
        "limit": limit,
        "offset": offset
    }


@router.post("")
async def create_inventory_item(
    item_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new inventory item"""
    new_item = Inventory(
        sku_code=item_data.get("sku_code"),
        title=item_data.get("title"),
        category=item_data.get("category"),
        condition=item_data.get("condition"),
        status=InventoryStatus[item_data.get("status", "AVAILABLE").upper()],
        storage=item_data.get("storage"),
        warehouse_id=item_data.get("warehouse_id"),
        cost=item_data.get("cost"),
        expected_price=item_data.get("expected_price"),
        image_url=item_data.get("image_url"),
        notes=item_data.get("notes"),
        quantity=item_data.get("quantity", 1),
    )
    
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    
    return {"id": new_item.id, "message": "Inventory item created"}


@router.put("/{item_id}")
async def update_inventory_item(
    item_id: int,
    item_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update inventory item"""
    item = db.query(Inventory).filter(Inventory.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    for key, value in item_data.items():
        if key == "status" and value:
            setattr(item, key, InventoryStatus[value.upper()])
        elif hasattr(item, key):
            setattr(item, key, value)
    
    db.commit()
    return {"id": item_id, "message": "Item updated"}


@router.delete("/{item_id}")
async def delete_inventory_item(
    item_id: int,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Delete inventory item (admin only)"""
    item = db.query(Inventory).filter(Inventory.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    db.delete(item)
    db.commit()
    return {"message": "Item deleted"}
