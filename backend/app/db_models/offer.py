from sqlalchemy import Column, String, DateTime, Numeric, Text, Integer, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Offer(Base):
    __tablename__ = "ebay_offers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    listing_id = Column(String(36), ForeignKey('ebay_listings.id', ondelete='SET NULL'), index=True)
    
    offer_id = Column(String(100), unique=True, nullable=False)
    ebay_listing_id = Column(String(100))
    
    buyer_username = Column(String(100), index=True)
    buyer_user_id = Column(String(100))
    
    offer_amount = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, default=1)
    offer_message = Column(Text)
    
    offer_status = Column(String(50), nullable=False, index=True)
    counter_offer_amount = Column(Numeric(10, 2))
    
    offer_date = Column(DateTime(timezone=True), nullable=False, index=True)
    expiration_date = Column(DateTime(timezone=True))
    response_date = Column(DateTime(timezone=True))
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
