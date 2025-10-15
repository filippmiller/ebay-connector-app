from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Refund(Base):
    __tablename__ = "ebay_refunds"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey('ebay_orders.id', ondelete='SET NULL'), index=True)
    
    refund_id = Column(String(100), unique=True, nullable=False)
    return_id = Column(String(100))
    case_id = Column(String(100))
    
    refund_amount = Column(Numeric(10, 2), nullable=False)
    refund_type = Column(String(50))
    refund_reason = Column(String(100))
    currency_code = Column(String(3), default='USD')
    
    refund_status = Column(String(50), nullable=False, index=True)
    
    refund_date = Column(DateTime(timezone=True), nullable=False, index=True)
    issued_date = Column(DateTime(timezone=True))
    
    buyer_note = Column(Text)
    seller_note = Column(Text)
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
