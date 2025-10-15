from sqlalchemy import Column, String, DateTime, Numeric, Text, Integer, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid

class Order(Base):
    __tablename__ = "ebay_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    order_id = Column(String(100), unique=True, nullable=False, index=True)
    legacy_order_id = Column(String(100))
    
    order_status = Column(String(50), nullable=False, index=True)
    order_date = Column(DateTime(timezone=True), nullable=False, index=True)
    last_modified_date = Column(DateTime(timezone=True))
    
    buyer_username = Column(String(100), index=True)
    buyer_email = Column(String(255))
    buyer_user_id = Column(String(100))
    buyer_checkout_message = Column(Text)
    
    shipping_address = Column(Text)
    shipping_service = Column(String(100))
    shipping_carrier = Column(String(50))
    tracking_number = Column(String(100))
    shipped_date = Column(DateTime(timezone=True))
    delivery_date = Column(DateTime(timezone=True))
    
    total_amount = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2))
    shipping_cost = Column(Numeric(10, 2))
    tax_amount = Column(Numeric(10, 2))
    currency_code = Column(String(3), default='USD')
    
    payment_method = Column(String(50))
    payment_date = Column(DateTime(timezone=True))
    payout_date = Column(DateTime(timezone=True))
    payout_id = Column(String(100))
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    
    line_items = relationship("OrderLineItem", back_populates="order", cascade="all, delete-orphan")

class OrderLineItem(Base):
    __tablename__ = "order_line_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey('ebay_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    
    line_item_id = Column(String(100), unique=True, nullable=False)
    listing_id = Column(String(100), index=True)
    sku = Column(String(100), index=True)
    
    title = Column(Text, nullable=False)
    item_location = Column(String(255))
    quantity = Column(Integer, nullable=False, default=1)
    
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    discount_amount = Column(Numeric(10, 2), default=0)
    
    image_url = Column(Text)
    condition = Column(String(50))
    category_id = Column(String(50))
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    order = relationship("Order", back_populates="line_items")
