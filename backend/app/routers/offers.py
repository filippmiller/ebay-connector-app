from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.db_models import Offer, Listing
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from pydantic import BaseModel

router = APIRouter(prefix="/offers", tags=["offers"])

class OfferResponse(BaseModel):
    id: str
    offer_id: str
    ebay_listing_id: Optional[str]
    buyer_username: Optional[str]
    offer_amount: float
    quantity: int
    offer_message: Optional[str]
    offer_status: str
    counter_offer_amount: Optional[float]
    offer_date: datetime
    expiration_date: Optional[datetime]
    listing_title: Optional[str] = None
    listing_price: Optional[float] = None

    class Config:
        from_attributes = True

class OfferAction(BaseModel):
    action: str
    counter_amount: Optional[float] = None

@router.get("/", response_model=List[OfferResponse])
async def get_offers(
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Offer).filter(Offer.user_id == current_user.id)
    
    if status:
        query = query.filter(Offer.offer_status == status)
    else:
        query = query.filter(Offer.offer_status == "PENDING")
    
    offers = query.order_by(Offer.offer_date.desc()).offset(skip).limit(limit).all()
    
    result = []
    for offer in offers:
        offer_dict = {
            "id": offer.id,
            "offer_id": offer.offer_id,
            "ebay_listing_id": offer.ebay_listing_id,
            "buyer_username": offer.buyer_username,
            "offer_amount": float(offer.offer_amount),
            "quantity": offer.quantity,
            "offer_message": offer.offer_message,
            "offer_status": offer.offer_status,
            "counter_offer_amount": float(offer.counter_offer_amount) if offer.counter_offer_amount else None,
            "offer_date": offer.offer_date,
            "expiration_date": offer.expiration_date,
            "listing_title": None,
            "listing_price": None
        }
        
        if offer.listing_id:
            listing = db.query(Listing).filter(Listing.id == offer.listing_id).first()
            if listing:
                offer_dict["listing_title"] = listing.title
                offer_dict["listing_price"] = float(listing.price)
        
        result.append(offer_dict)
    
    return result

@router.post("/{offer_id}/action")
async def handle_offer_action(
    offer_id: str,
    action: OfferAction,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    offer = db.query(Offer).filter(
        Offer.id == offer_id,
        Offer.user_id == current_user.id
    ).first()
    
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    
    if offer.offer_status != "PENDING":
        raise HTTPException(status_code=400, detail="Offer is not pending")
    
    if action.action == "accept":
        offer.offer_status = "ACCEPTED"
        offer.response_date = datetime.utcnow()
    elif action.action == "decline":
        offer.offer_status = "DECLINED"
        offer.response_date = datetime.utcnow()
    elif action.action == "counter":
        if not action.counter_amount:
            raise HTTPException(status_code=400, detail="Counter amount is required")
        offer.offer_status = "COUNTERED"
        offer.counter_offer_amount = action.counter_amount
        offer.response_date = datetime.utcnow()
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    db.commit()
    db.refresh(offer)
    
    return {"message": f"Offer {action.action}ed successfully"}

@router.get("/stats/summary")
async def get_offer_stats(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func
    
    pending_count = db.query(func.count(Offer.id)).filter(
        Offer.user_id == current_user.id,
        Offer.offer_status == "PENDING"
    ).scalar()
    
    status_counts = db.query(
        Offer.offer_status,
        func.count(Offer.id)
    ).filter(Offer.user_id == current_user.id).group_by(Offer.offer_status).all()
    
    return {
        "pending_count": pending_count,
        "status_breakdown": {status: count for status, count in status_counts}
    }
