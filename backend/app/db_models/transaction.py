from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Transaction(Base):
    __tablename__ = "ebay_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey('ebay_orders.id', ondelete='SET NULL'), index=True)
    
    transaction_id = Column(String(100), unique=True, nullable=False)
    transaction_type = Column(String(50), nullable=False, index=True)
    
    amount = Column(Numeric(10, 2), nullable=False)
    currency_code = Column(String(3), default='USD')
    fee_amount = Column(Numeric(10, 2), default=0)
    net_amount = Column(Numeric(10, 2), nullable=False)
    
    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    description = Column(Text)
    reference_id = Column(String(100))
    
    transaction_status = Column(String(50))
    payout_id = Column(String(100), index=True)
    payout_date = Column(DateTime(timezone=True))
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
