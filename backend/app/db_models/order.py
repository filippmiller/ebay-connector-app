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
    """Line items for orders, mapped to public.order_line_items in Supabase.

    Minimal subset aligned with the real table schema so grids can safely query
    without referencing non-existent columns.
    """

    __tablename__ = "order_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # NOTE: In Supabase this is a varchar FK to the external order identifier.
    # We keep it as String here and do not join to ebay_orders for now.
    order_id = Column(String(255), nullable=False, index=True)

    line_item_id = Column(String(255), nullable=False, index=True)
    sku = Column(String(255), nullable=True, index=True)
    title = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=True)
    total_value = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(10), nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    ebay_account_id = Column(String(255), nullable=True, index=True)
    ebay_user_id = Column(String(255), nullable=True, index=True)

    # No relationship to Order here in the minimal version; the grid only uses
    # this table. We can reintroduce joins/enrichments once the basic grid is stable.
    order = relationship("Order", back_populates="line_items", viewonly=True, primaryjoin="foreign(OrderLineItem.order_id) == Order.order_id")
