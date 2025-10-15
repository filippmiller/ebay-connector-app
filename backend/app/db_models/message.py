from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Message(Base):
    __tablename__ = "ebay_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey('ebay_orders.id', ondelete='SET NULL'), index=True)
    listing_id = Column(String(36), ForeignKey('ebay_listings.id', ondelete='SET NULL'), index=True)
    
    message_id = Column(String(100), unique=True, nullable=False)
    thread_id = Column(String(100), index=True)
    parent_message_id = Column(String(100))
    
    sender_username = Column(String(100))
    sender_user_id = Column(String(100))
    recipient_username = Column(String(100))
    recipient_user_id = Column(String(100))
    
    subject = Column(Text)
    body = Column(Text, nullable=False)
    message_type = Column(String(50))
    
    is_read = Column(Boolean, default=False, index=True)
    is_flagged = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    direction = Column(String(20), nullable=False)
    
    message_date = Column(DateTime(timezone=True), nullable=False, index=True)
    read_date = Column(DateTime(timezone=True))
    
    raw_data = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
