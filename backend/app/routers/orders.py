from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.db_models import Order, OrderLineItem
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from pydantic import BaseModel

router = APIRouter(prefix="/orders", tags=["orders"])

class OrderLineItemResponse(BaseModel):
    id: str
    line_item_id: str
    listing_id: Optional[str]
    sku: Optional[str]
    title: str
    quantity: int
    unit_price: float
    total_price: float
    image_url: Optional[str]
    condition: Optional[str]

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: str
    order_id: str
    order_status: str
    order_date: datetime
    buyer_username: Optional[str]
    buyer_email: Optional[str]
    total_amount: float
    shipping_cost: Optional[float]
    tax_amount: Optional[float]
    tracking_number: Optional[str]
    shipped_date: Optional[datetime]
    line_items: List[OrderLineItemResponse] = []

    class Config:
        from_attributes = True

@router.get("/", response_model=List[OrderResponse])
async def get_orders(
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Order).filter(Order.user_id == current_user.id)
    
    if status:
        query = query.filter(Order.order_status == status)
    
    if search:
        query = query.filter(
            (Order.order_id.contains(search)) |
            (Order.buyer_username.contains(search)) |
            (Order.buyer_email.contains(search))
        )
    
    orders = query.order_by(Order.order_date.desc()).offset(skip).limit(limit).all()
    return orders

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order

@router.get("/stats/summary")
async def get_order_stats(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func
    
    total_orders = db.query(func.count(Order.id)).filter(Order.user_id == current_user.id).scalar()
    
    total_revenue = db.query(func.sum(Order.total_amount)).filter(
        Order.user_id == current_user.id,
        Order.order_status.in_(['PAID', 'SHIPPED', 'COMPLETED'])
    ).scalar() or 0
    
    status_counts = db.query(
        Order.order_status,
        func.count(Order.id)
    ).filter(Order.user_id == current_user.id).group_by(Order.order_status).all()
    
    return {
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "status_breakdown": {status: count for status, count in status_counts}
    }
