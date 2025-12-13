from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

from app.models_sqlalchemy import get_db
from app.db_models.inventory_offer import EbayInventoryOfferEvent
from app.services.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/inventory-offers", tags=["inventory-offers"])

class OfferHistoryEvent(BaseModel):
    id: str
    event_type: str
    fetched_at: Optional[datetime]
    changed_fields: Optional[Any]
    snapshot_payload: Optional[Any]
    price_value: Optional[float]
    available_quantity: Optional[int]
    status: Optional[str]

    class Config:
        from_attributes = True

@router.get("/{offer_id}/history", response_model=List[OfferHistoryEvent])
async def get_offer_history(
    offer_id: str,
    account_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get history events for a specific offer."""
    query = db.query(EbayInventoryOfferEvent).filter(EbayInventoryOfferEvent.offer_id == offer_id)
    
    if account_id:
        query = query.filter(EbayInventoryOfferEvent.ebay_account_id == account_id)
        
    # TODO: Ensure user has access to this account/offer
    
    events = query.order_by(desc(EbayInventoryOfferEvent.fetched_at)).limit(limit).all()
    return events

@router.get("/history", response_model=List[OfferHistoryEvent])
async def get_offer_history_by_sku(
    sku: str = Query(..., min_length=1),
    account_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get history events for a specific SKU."""
    query = db.query(EbayInventoryOfferEvent).filter(EbayInventoryOfferEvent.sku == sku)
    
    if account_id:
        query = query.filter(EbayInventoryOfferEvent.ebay_account_id == account_id)
        
    events = query.order_by(desc(EbayInventoryOfferEvent.fetched_at)).limit(limit).all()
    return events
