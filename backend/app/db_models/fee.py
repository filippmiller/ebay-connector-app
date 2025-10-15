from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Fee(Base):
    __tablename__ = "ebay_fees"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey('ebay_orders.id', ondelete='SET NULL'), index=True)
    listing_id = Column(String(36), ForeignKey('ebay_listings.id', ondelete='SET NULL'), index=True)
    
    fee_id = Column(String(100), unique=True, nullable=False)
    fee_type = Column(String(50), nullable=False, index=True)
    
    fee_amount = Column(Numeric(10, 2), nullable=False)
    currency_code = Column(String(3), default='USD')
    
    fee_date = Column(DateTime(timezone=True), nullable=False, index=True)
    description = Column(Text)
    reference_id = Column(String(100))
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
