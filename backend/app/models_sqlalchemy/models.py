from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum, Boolean, Index, Numeric, CHAR, desc
from sqlalchemy.dialects.postgresql import JSONB
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


class PaymentStatus(str, enum.Enum):
    PAID = "PAID"
    NOT_PAID = "NOT_PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class FulfillmentStatus(str, enum.Enum):
    FULFILLED = "FULFILLED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    NOT_STARTED = "NOT_STARTED"
    UNKNOWN = "UNKNOWN"


class ConditionType(str, enum.Enum):
    new = "new"
    refurbished = "refurbished"
    used_excellent = "used_excellent"
    used_good = "used_good"
    used_acceptable = "used_acceptable"
    for_parts = "for_parts"


class InventoryStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    LISTED = "LISTED"
    SOLD = "SOLD"
    FROZEN = "FROZEN"
    REPAIR = "REPAIR"
    RETURNED = "RETURNED"
    PENDING_LISTING = "PENDING_LISTING"
    available = "AVAILABLE"
    listed = "LISTED"
    sold = "SOLD"
    frozen = "FROZEN"
    reserved = "FROZEN"


class ProfitStatus(str, enum.Enum):
    OK = "OK"
    NEGATIVE = "NEGATIVE"
    INCOMPLETE = "INCOMPLETE"


class FeeType(str, enum.Enum):
    FINAL_VALUE_FEE = "FINAL_VALUE_FEE"
    AD_FEE = "AD_FEE"
    SHIPPING_LABEL = "SHIPPING_LABEL"
    OTHER = "OTHER"


class PayoutStatus(str, enum.Enum):
    PAID = "PAID"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"


class PayoutItemType(str, enum.Enum):
    ORDER = "ORDER"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"
    FEE_REVERSAL = "FEE_REVERSAL"
    OTHER = "OTHER"


class OfferDirection(str, enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class OfferState(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    COUNTERED = "COUNTERED"
    SENT = "SENT"


class OfferAction(str, enum.Enum):
    SEND = "SEND"
    ACCEPT = "ACCEPT"
    DECLINE = "DECLINE"
    COUNTER = "COUNTER"
    EXPIRE = "EXPIRE"
    WITHDRAW = "WITHDRAW"


class OfferActor(str, enum.Enum):
    SYSTEM = "SYSTEM"
    ADMIN = "ADMIN"


class EbayStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


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
    ebay_access_token = Column(Text, nullable=True)  # Production token
    ebay_refresh_token = Column(Text, nullable=True)  # Production refresh token
    ebay_token_expires_at = Column(DateTime, nullable=True)  # Production token expires
    ebay_environment = Column(String(20), default="sandbox")
    
    # Sandbox tokens (separate from production)
    ebay_sandbox_access_token = Column(Text, nullable=True)
    ebay_sandbox_refresh_token = Column(Text, nullable=True)
    ebay_sandbox_token_expires_at = Column(DateTime, nullable=True)
    
    sync_logs = relationship("SyncLog", back_populates="user")
    sync_event_logs = relationship("SyncEventLog", back_populates="user")
    
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
    sku_id = Column(Integer, ForeignKey('sku.id'), nullable=True)
    sku_code = Column(String(100), nullable=True, index=True)
    model = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)
    condition = Column(Enum(ConditionType), nullable=True, index=True)
    part_number = Column(String(100), nullable=True, index=True)
    title = Column(Text, nullable=True)
    
    price_value = Column(Numeric(14, 2), nullable=True)
    price_currency = Column(CHAR(3), nullable=True)
    
    ebay_listing_id = Column(String(100), nullable=True, index=True)
    ebay_status = Column(Enum(EbayStatus), nullable=True, index=True)
    
    status = Column(Enum(InventoryStatus), default=InventoryStatus.AVAILABLE, index=True)
    photo_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    
    storage_id = Column(String(100), nullable=True, index=True)
    storage = Column(String(100), nullable=True, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True, index=True)
    
    quantity = Column(Integer, default=1)
    
    rec_created = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    rec_updated = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    author = Column(String(100), nullable=True, index=True)
    
    buyer_info = Column(Text, nullable=True)
    tracking_number = Column(String(100), nullable=True, index=True)
    raw_payload = Column(JSONB, nullable=True)
    
    sku = relationship("SKU", back_populates="inventory_items")
    warehouse = relationship("Warehouse", back_populates="inventory_items")
    
    __table_args__ = (
        Index('idx_inventory_sku_id', 'sku_id'),
        Index('idx_inventory_sku_code', 'sku_code'),
        Index('idx_inventory_category', 'category'),
        Index('idx_inventory_condition', 'condition'),
        Index('idx_inventory_status', 'status'),
        Index('idx_inventory_ebay_status', 'ebay_status'),
        Index('idx_inventory_warehouse_id', 'warehouse_id'),
        Index('idx_inventory_storage', 'storage'),
        Index('idx_inventory_storage_id', 'storage_id'),
        Index('idx_inventory_author', 'author'),
        Index('idx_inventory_part_number', 'part_number'),
        Index('idx_inventory_tracking', 'tracking_number'),
        Index('idx_inventory_ebay_listing', 'ebay_listing_id'),
        Index('idx_inventory_created_desc', desc(rec_created)),
        Index('idx_composite_status_warehouse', 'status', 'warehouse_id'),
        Index('idx_composite_storage_status', 'storage_id', 'status'),
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
    job_id = Column(String(100), unique=True, nullable=True, index=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    endpoint = Column(String(255), nullable=False)
    
    pages_fetched = Column(Integer, default=0)
    records_fetched = Column(Integer, default=0)
    records_stored = Column(Integer, default=0)
    record_count = Column(Integer, default=0)
    
    duration = Column(Float, default=0.0)
    duration_ms = Column(Integer, default=0)
    
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    error_text = Column(Text, nullable=True)
    
    sync_started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sync_completed_at = Column(DateTime, nullable=True)
    
    rec_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    user = relationship("User", back_populates="sync_logs")
    
    __table_args__ = (
        Index('idx_synclog_job_id', 'job_id'),
        Index('idx_synclog_user_id', 'user_id'),
        Index('idx_synclog_status', 'status'),
        Index('idx_synclog_started', 'sync_started_at'),
    )


class SyncEventLog(Base):
    """Detailed event-level logs for sync operations with real-time streaming support"""
    __tablename__ = "sync_event_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(100), nullable=False, index=True)  # Correlation ID for grouping events
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    sync_type = Column(String(50), nullable=False)  # 'orders', 'transactions', 'disputes', 'offers'
    
    event_type = Column(String(50), nullable=False)  # 'start', 'progress', 'log', 'http', 'error', 'done'
    level = Column(String(20), nullable=False, default='info')  # 'debug', 'info', 'warning', 'error'
    message = Column(Text, nullable=False)
    
    http_method = Column(String(10), nullable=True)
    http_url = Column(Text, nullable=True)
    http_status = Column(Integer, nullable=True)
    http_duration_ms = Column(Integer, nullable=True)
    
    current_page = Column(Integer, nullable=True)
    total_pages = Column(Integer, nullable=True)
    items_fetched = Column(Integer, nullable=True)
    items_stored = Column(Integer, nullable=True)
    progress_pct = Column(Float, nullable=True)
    
    extra_data = Column(JSONB, nullable=True)
    
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    user = relationship("User", back_populates="sync_event_logs")
    
    __table_args__ = (
        Index('idx_sync_event_run_id', 'run_id'),
        Index('idx_sync_event_user_id', 'user_id'),
        Index('idx_sync_event_type', 'event_type'),
        Index('idx_sync_event_timestamp', 'timestamp'),
        Index('idx_sync_event_run_timestamp', 'run_id', 'timestamp'),
    )


class EbayConnectLog(Base):
    __tablename__ = "ebay_connect_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True, index=True)
    environment = Column(String(20), nullable=False, default="sandbox", index=True)
    action = Column(String(50), nullable=False, index=True)

    request_method = Column(String(10), nullable=True)
    request_url = Column(Text, nullable=True)
    request_headers = Column(JSONB, nullable=True)
    request_body = Column(JSONB, nullable=True)

    response_status = Column(Integer, nullable=True)
    response_headers = Column(JSONB, nullable=True)
    response_body = Column(JSONB, nullable=True)

    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = relationship("User", backref="ebay_connect_logs")

    __table_args__ = (
        Index('idx_ebay_connect_logs_user_env', 'user_id', 'environment'),
        Index('idx_ebay_connect_logs_action', 'action'),
        Index('idx_ebay_connect_logs_created', 'created_at'),
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


class Purchase(Base):
    __tablename__ = "purchases"
    
    purchase_id = Column(String(100), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    
    creation_date = Column(DateTime(timezone=True), nullable=True)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    
    buyer_username = Column(String(100), nullable=True, index=True)
    seller_username = Column(String(100), nullable=True, index=True)
    
    total_value = Column(Numeric(14, 2), nullable=True)
    total_currency = Column(CHAR(3), nullable=True)
    
    payment_status = Column(Enum(PaymentStatus), nullable=True, index=True)
    fulfillment_status = Column(Enum(FulfillmentStatus), nullable=True, index=True)
    
    tracking_number = Column(String(100), nullable=True)
    ship_to_name = Column(String(255), nullable=True)
    ship_to_city = Column(String(100), nullable=True)
    ship_to_state = Column(String(100), nullable=True)
    ship_to_postal = Column(String(20), nullable=True)
    ship_to_country = Column(CHAR(2), nullable=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    line_items = relationship("PurchaseLineItem", back_populates="purchase", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_purchase_creation_date', 'creation_date'),
        Index('idx_purchase_buyer', 'buyer_username'),
        Index('idx_purchase_seller', 'seller_username'),
        Index('idx_purchase_payment_status', 'payment_status'),
        Index('idx_purchase_fulfillment_status', 'fulfillment_status'),
        Index('idx_purchase_user_id', 'user_id'),
    )


class PurchaseLineItem(Base):
    __tablename__ = "purchase_line_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(String(100), ForeignKey('purchases.purchase_id'), nullable=False)
    line_item_id = Column(String(100), nullable=False)
    
    sku = Column(String(100), nullable=True, index=True)
    title = Column(Text, nullable=True)
    quantity = Column(Integer, default=0)
    total_value = Column(Numeric(14, 2), nullable=True)
    currency = Column(CHAR(3), nullable=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    purchase = relationship("Purchase", back_populates="line_items")
    
    __table_args__ = (
        Index('idx_purch_line_purchase_id', 'purchase_id'),
        Index('idx_purch_line_sku', 'sku'),
        Index('idx_purch_line_unique', 'purchase_id', 'line_item_id', unique=True),
    )


class Transaction(Base):
    __tablename__ = "transactions"
    
    transaction_id = Column(String(100), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    
    order_id = Column(String(100), nullable=True, index=True)
    line_item_id = Column(String(100), nullable=True)
    sku = Column(String(100), nullable=True, index=True)
    
    buyer_username = Column(String(100), nullable=True, index=True)
    sale_value = Column(Numeric(14, 2), nullable=True)
    currency = Column(CHAR(3), nullable=True)
    sale_date = Column(DateTime(timezone=True), nullable=True, index=True)
    
    quantity = Column(Integer, default=0)
    shipping_charged = Column(Numeric(14, 2), nullable=True)
    tax_collected = Column(Numeric(14, 2), nullable=True)
    
    fulfillment_status = Column(Enum(FulfillmentStatus), nullable=True)
    payment_status = Column(Enum(PaymentStatus), nullable=True)
    
    profit = Column(Numeric(14, 2), nullable=True)
    profit_status = Column(Enum(ProfitStatus), nullable=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_txn_order_id', 'order_id'),
        Index('idx_txn_sale_date', 'sale_date'),
        Index('idx_txn_buyer', 'buyer_username'),
        Index('idx_txn_sku', 'sku'),
        Index('idx_txn_user_id', 'user_id'),
    )


class Fee(Base):
    __tablename__ = "fees"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    
    source_type = Column(String(50), nullable=True)
    source_id = Column(String(100), nullable=True, index=True)
    fee_type = Column(String(100), nullable=True, index=True)
    
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(CHAR(3), nullable=True)
    assessed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_fee_source_id', 'source_id'),
        Index('idx_fee_type', 'fee_type'),
        Index('idx_fee_assessed_at', 'assessed_at'),
        Index('idx_fee_user_id', 'user_id'),
    )


class Payout(Base):
    __tablename__ = "payouts"
    
    payout_id = Column(String(100), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    
    total_amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(CHAR(3), nullable=True)
    status = Column(Enum(PayoutStatus), nullable=True)
    payout_date = Column(DateTime(timezone=True), nullable=True, index=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to payout items
    payout_items = relationship("PayoutItem", back_populates="payout", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_payout_date', 'payout_date'),
        Index('idx_payout_user_id', 'user_id'),
    )


class UserGridLayout(Base):
    __tablename__ = "user_grid_layouts"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    grid_key = Column(String(100), nullable=False)
    
    # Ordered list of visible column names
    visible_columns = Column(JSONB, nullable=True)
    # Mapping column_name -> width in pixels
    column_widths = Column(JSONB, nullable=True)
    # Optional sort config: { "column": str, "direction": "asc"|"desc" }
    sort = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_user_grid_layouts_user_grid', 'user_id', 'grid_key', unique=True),
    )


class PayoutItem(Base):
    __tablename__ = "payout_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    payout_id = Column(String(100), ForeignKey('payouts.payout_id'), nullable=False)
    
    type = Column(String(50), nullable=True)
    reference_id = Column(String(100), nullable=True, index=True)
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(CHAR(3), nullable=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    payout = relationship("Payout", back_populates="payout_items")
    
    __table_args__ = (
        Index('idx_payout_item_payout_id', 'payout_id'),
        Index('idx_payout_item_reference_id', 'reference_id'),
    )


class Offer(Base):
    __tablename__ = "offers"
    
    offer_id = Column(String(100), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    
    direction = Column(Enum(OfferDirection), nullable=False, index=True)
    state = Column(Enum(OfferState), nullable=False, default=OfferState.PENDING, index=True)
    
    item_id = Column(String(100), nullable=True, index=True)
    sku = Column(String(100), nullable=True, index=True)
    buyer_username = Column(String(100), nullable=True, index=True)
    
    quantity = Column(Integer, default=1)
    price_value = Column(Numeric(14, 2), nullable=True)
    price_currency = Column(CHAR(3), nullable=True)
    original_price_value = Column(Numeric(14, 2), nullable=True)
    original_price_currency = Column(CHAR(3), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    message = Column(Text, nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    
    actions = relationship("OfferActionLog", back_populates="offer", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_offer_item_id', 'item_id'),
        Index('idx_offer_state', 'state'),
        Index('idx_offer_direction', 'direction'),
        Index('idx_offer_created_at', 'created_at'),
        Index('idx_offer_buyer', 'buyer_username'),
        Index('idx_offer_sku', 'sku'),
        Index('idx_offer_user_id', 'user_id'),
    )


class OfferActionLog(Base):
    __tablename__ = "offer_actions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(String(100), ForeignKey('offers.offer_id', ondelete='CASCADE'), nullable=False, index=True)
    
    action = Column(Enum(OfferAction), nullable=False)
    actor = Column(Enum(OfferActor), nullable=False, default=OfferActor.SYSTEM)
    notes = Column(Text, nullable=True)
    result_state = Column(Enum(OfferState), nullable=True)
    
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    offer = relationship("Offer", back_populates="actions")
    
    __table_args__ = (
        Index('idx_offer_action_offer_id', 'offer_id'),
        Index('idx_offer_action_created_at', 'created_at'),
    )


class EbayAccount(Base):
    __tablename__ = "ebay_accounts"
    
    id = Column(String(36), primary_key=True)
    org_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ebay_user_id = Column(Text, nullable=False)
    username = Column(Text, nullable=True)
    house_name = Column(Text, nullable=False)
    purpose = Column(Text, nullable=True, server_default='BOTH')
    marketplace_id = Column(Text, nullable=True)
    site_id = Column(Integer, nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, server_default='true')
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    tokens = relationship("EbayToken", back_populates="account", uselist=False, cascade="all, delete-orphan")
    authorizations = relationship("EbayAuthorization", back_populates="account", cascade="all, delete-orphan")
    sync_cursors = relationship("EbaySyncCursor", back_populates="account", cascade="all, delete-orphan")
    health_events = relationship("EbayHealthEvent", back_populates="account", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_ebay_accounts_org_id', 'org_id'),
        Index('idx_ebay_accounts_ebay_user_id', 'ebay_user_id'),
        Index('idx_ebay_accounts_house_name', 'house_name'),
        Index('idx_ebay_accounts_is_active', 'is_active'),
    )


class EbayToken(Base):
    __tablename__ = "ebay_tokens"
    
    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_type = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    refresh_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = relationship("EbayAccount", back_populates="tokens")
    
    __table_args__ = (
        Index('idx_ebay_tokens_account_id', 'ebay_account_id'),
        Index('idx_ebay_tokens_expires_at', 'expires_at'),
    )


class EbayAuthorization(Base):
    __tablename__ = "ebay_authorizations"
    
    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    scopes = Column(JSONB, nullable=False, server_default='[]')
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = relationship("EbayAccount", back_populates="authorizations")
    
    __table_args__ = (
        Index('idx_ebay_authorizations_account_id', 'ebay_account_id'),
    )


class EbaySyncCursor(Base):
    __tablename__ = "ebay_sync_cursors"
    
    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    resource = Column(Text, nullable=False)
    checkpoint = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = relationship("EbayAccount", back_populates="sync_cursors")
    
    __table_args__ = (
        Index('idx_ebay_sync_cursors_account_id', 'ebay_account_id'),
        Index('idx_ebay_sync_cursors_resource', 'resource'),
    )


class EbayHealthEvent(Base):
    __tablename__ = "ebay_health_events"
    
    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    checked_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    is_healthy = Column(Boolean, nullable=False)
    http_status = Column(Integer, nullable=True)
    ack = Column(Text, nullable=True)
    error_code = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    
    account = relationship("EbayAccount", back_populates="health_events")
    
    __table_args__ = (
        Index('idx_ebay_health_events_account_id', 'ebay_account_id'),
        Index('idx_ebay_health_events_checked_at', 'checked_at'),
        Index('idx_ebay_health_events_is_healthy', 'is_healthy'),
    )


class Message(Base):
    __tablename__ = "ebay_messages"
    
    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    house_name = Column(Text, nullable=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    message_id = Column(String(100), nullable=False)
    thread_id = Column(String(100), nullable=True)
    sender_username = Column(String(100), nullable=True)
    recipient_username = Column(String(100), nullable=True)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    message_type = Column(String(50), nullable=True)
    is_read = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    direction = Column(String(20), nullable=True)
    message_date = Column(DateTime(timezone=True), nullable=True)
    read_date = Column(DateTime(timezone=True), nullable=True)
    order_id = Column(String(100), nullable=True)
    listing_id = Column(String(100), nullable=True)
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ebay_messages_account_id', 'ebay_account_id'),
        Index('idx_ebay_messages_user_id', 'user_id'),
        Index('idx_ebay_messages_message_id', 'message_id'),
        Index('idx_ebay_messages_thread_id', 'thread_id'),
        Index('idx_ebay_messages_is_read', 'is_read'),
        Index('idx_ebay_messages_message_date', 'message_date'),
    )


class ActiveInventory(Base):
    """Snapshot of active listings from Feed Active Inventory Report per account."""
    __tablename__ = "ebay_active_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    ebay_user_id = Column(Text, nullable=True)
    sku = Column(String(100), nullable=True, index=True)
    item_id = Column(String(100), nullable=True, index=True)
    title = Column(Text, nullable=True)
    quantity_available = Column(Integer, nullable=True)
    price = Column(Numeric(14, 2), nullable=True)
    currency = Column(CHAR(3), nullable=True)
    listing_status = Column(String(50), nullable=True, index=True)
    condition_id = Column(String(50), nullable=True)
    condition_text = Column(Text, nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_active_inv_account_sku_item', 'ebay_account_id', 'sku', 'item_id', unique=True),
        Index('idx_active_inv_ebay_user_id', 'ebay_user_id'),
    )


class EbayScopeDefinition(Base):
    __tablename__ = "ebay_scope_definitions"

    id = Column(String(36), primary_key=True)
    scope = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    grant_type = Column(String(20), nullable=False, default="user")  # 'user', 'client', or 'both'
    is_active = Column(Boolean, nullable=False, default=True)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_ebay_scope_definitions_scope', 'scope', unique=True),
        Index('idx_ebay_scope_definitions_grant_type', 'grant_type'),
    )
