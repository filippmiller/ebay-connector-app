from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from . import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    purchaser = "purchaser"
    lister = "lister"
    checker = "checker"
    viewer = "viewer"
    user = "user"


class OrderStatus(str, enum.Enum):
    unpaid = "unpaid"
    in_transit = "in_transit"
    received = "received"
    cancelled = "cancelled"
    completed = "completed"


class ConditionType(str, enum.Enum):
    new = "new"
    refurbished = "refurbished"
    used_excellent = "used_excellent"
    used_good = "used_good"
    used_acceptable = "used_acceptable"
    for_parts = "for_parts"


class InventoryStatus(str, enum.Enum):
    available = "available"
    listed = "listed"
    sold = "sold"
    frozen = "frozen"
    reserved = "reserved"


class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.user)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    ebay_connected = Column(Boolean, default=False)
    ebay_access_token = Column(Text, nullable=True)
    ebay_refresh_token = Column(Text, nullable=True)
    ebay_token_expires_at = Column(DateTime, nullable=True)
    ebay_environment = Column(String(20), default="sandbox")
    
    sync_logs = relationship("SyncLog", back_populates="user")
    
    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_role', 'role'),
    )


class Buying(Base):
    __tablename__ = "buying"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(100), unique=True, nullable=False, index=True)
    tracking_number = Column(String(100), nullable=True)
    
    buyer_id = Column(String(100), index=True)
    buyer_username = Column(String(100))
    seller_id = Column(String(100), index=True)
    seller_username = Column(String(100))
    
    title = Column(Text, nullable=False)
    paid_date = Column(DateTime, nullable=True)
    amount_paid = Column(Float, default=0.0)
    sale_price = Column(Float, default=0.0)
    ebay_fee = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    refund = Column(Float, default=0.0)
    profit = Column(Float, default=0.0)
    
    status = Column(Enum(OrderStatus), default=OrderStatus.unpaid)
    storage = Column(String(100), nullable=True)
    comment = Column(Text, nullable=True)
    author = Column(String(100), nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_buying_item_id', 'item_id'),
        Index('idx_buying_buyer_id', 'buyer_id'),
        Index('idx_buying_seller_id', 'seller_id'),
        Index('idx_buying_status', 'status'),
        Index('idx_buying_paid_date', 'paid_date'),
    )


class Warehouse(Base):
    __tablename__ = "warehouses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    location = Column(String(255), nullable=True)
    capacity = Column(Integer, default=0)
    warehouse_type = Column(String(50), nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    inventory_items = relationship("Inventory", back_populates="warehouse")


class SKU(Base):
    __tablename__ = "sku"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sku_code = Column(String(100), unique=True, nullable=False, index=True)
    model = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    condition = Column(Enum(ConditionType), nullable=True)
    part_number = Column(String(100), nullable=True)
    price = Column(Float, default=0.0)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    brand = Column(String(100), nullable=True)
    image_url = Column(Text, nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    listings = relationship("Listing", back_populates="sku")
    inventory_items = relationship("Inventory", back_populates="sku")
    
    __table_args__ = (
        Index('idx_sku_code', 'sku_code'),
        Index('idx_sku_category', 'category'),
    )


class Listing(Base):
    __tablename__ = "listings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sku_id = Column(Integer, ForeignKey('sku.id'), nullable=False)
    ebay_listing_id = Column(String(100), unique=True, nullable=False, index=True)
    ebay_item_id = Column(String(100), nullable=True, index=True)
    
    price = Column(Float, default=0.0)
    ebay_price = Column(Float, default=0.0)
    shipping_group = Column(String(100), nullable=True)
    condition = Column(Enum(ConditionType), nullable=True)
    storage = Column(String(100), nullable=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    
    is_active = Column(Boolean, default=True)
    listed_date = Column(DateTime, nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    sku = relationship("SKU", back_populates="listings")
    
    __table_args__ = (
        Index('idx_listing_ebay_id', 'ebay_listing_id'),
        Index('idx_listing_item_id', 'ebay_item_id'),
        Index('idx_listing_sku_id', 'sku_id'),
    )


class Inventory(Base):
    __tablename__ = "inventory"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sku_id = Column(Integer, ForeignKey('sku.id'), nullable=False)
    storage = Column(String(100), nullable=True)
    status = Column(Enum(InventoryStatus), default=InventoryStatus.available)
    category = Column(String(100), nullable=True)
    price = Column(Float, default=0.0)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    quantity = Column(Integer, default=1)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    sku = relationship("SKU", back_populates="inventory_items")
    warehouse = relationship("Warehouse", back_populates="inventory_items")
    
    __table_args__ = (
        Index('idx_inventory_sku_id', 'sku_id'),
        Index('idx_inventory_status', 'status'),
        Index('idx_inventory_warehouse_id', 'warehouse_id'),
    )


class Return(Base):
    __tablename__ = "returns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    return_id = Column(String(100), unique=True, nullable=False, index=True)
    item_id = Column(String(100), nullable=True)
    ebay_order_id = Column(String(100), nullable=True, index=True)
    
    buyer = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    reason = Column(Text, nullable=True)
    sale_price = Column(Float, default=0.0)
    refund_amount = Column(Float, default=0.0)
    status = Column(String(50), nullable=True)
    comment = Column(Text, nullable=True)
    
    return_date = Column(DateTime, nullable=True)
    resolved_date = Column(DateTime, nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_return_return_id', 'return_id'),
        Index('idx_return_order_id', 'ebay_order_id'),
    )


class SyncLog(Base):
    __tablename__ = "sync_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    endpoint = Column(String(255), nullable=False)
    record_count = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    
    sync_started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sync_completed_at = Column(DateTime, nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    user = relationship("User", back_populates="sync_logs")
    
    __table_args__ = (
        Index('idx_synclog_user_id', 'user_id'),
        Index('idx_synclog_status', 'status'),
        Index('idx_synclog_started', 'sync_started_at'),
    )


class Report(Base):
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(100), nullable=False)
    filters = Column(Text, nullable=True)
    file_path = Column(String(255), nullable=True)
    generated_by = Column(String(36), ForeignKey('users.id'), nullable=True)
    
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_report_type', 'report_type'),
        Index('idx_report_generated_at', 'generated_at'),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    token = Column(String(36), primary_key=True)
    email = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    
    __table_args__ = (
        Index('idx_reset_token_email', 'email'),
        Index('idx_reset_token_expires', 'expires_at'),
    )
