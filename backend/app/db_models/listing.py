from sqlalchemy import Column, String, DateTime, Numeric, Text, Integer, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Listing(Base):
    __tablename__ = "ebay_listings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    listing_id = Column(String(100), unique=True, nullable=False, index=True)
    sku = Column(String(100), index=True)
    
    title = Column(Text, nullable=False)
    description = Column(Text)
    subtitle = Column(Text)
    category_id = Column(String(50))
    category_name = Column(String(255))
    
    listing_status = Column(String(50), nullable=False, index=True)
    quantity_available = Column(Integer, default=0)
    quantity_sold = Column(Integer, default=0)
    
    price = Column(Numeric(10, 2), nullable=False)
    currency_code = Column(String(3), default='USD')
    listing_type = Column(String(50))
    
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    
    primary_image_url = Column(Text)
    image_urls = Column(Text)
    
    condition = Column(String(50))
    condition_description = Column(Text)
    location = Column(String(255))
    shipping_options = Column(Text)
    return_policy = Column(Text)
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
