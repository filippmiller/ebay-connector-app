from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    ebay_connected = Column(Boolean, default=False)
    ebay_user_id = Column(String(100), index=True)
    ebay_access_token = Column(Text)
    ebay_refresh_token = Column(Text)
    ebay_token_expires_at = Column(DateTime(timezone=True))
    ebay_marketplace_id = Column(String(50), default='EBAY_US')
    ebay_last_sync_at = Column(DateTime(timezone=True))
    
    notification_preferences = Column(Text, default='{}')
    display_preferences = Column(Text, default='{}')
