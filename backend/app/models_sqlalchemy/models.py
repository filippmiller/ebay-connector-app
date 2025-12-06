from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, Date, Text, ForeignKey, Enum, Boolean, Index, Numeric, CHAR, desc, Table, inspect, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.exc import NoSuchTableError, OperationalError
from datetime import datetime
import enum
import uuid

from . import Base, engine
from app.utils.logger import logger


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
    # Soft-activation flag; inactive users cannot access the application.
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Global toggle for worker completion notifications (persistent per user)
    worker_notifications_enabled = Column(Boolean, nullable=False, default=True)

    # When True, the user is forced to pick a new password on next login.
    must_change_password = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    ebay_connected = Column(Boolean, default=False)
    # Underlying columns store encrypted values when written through the
    # properties below; the physical column names remain unchanged.
    _ebay_access_token = Column("ebay_access_token", Text, nullable=True)
    _ebay_refresh_token = Column("ebay_refresh_token", Text, nullable=True)
    ebay_token_expires_at = Column(DateTime, nullable=True)  # Production token expires
    ebay_environment = Column(String(20), default="sandbox")
    
    # Sandbox tokens (separate from production)
    _ebay_sandbox_access_token = Column("ebay_sandbox_access_token", Text, nullable=True)
    _ebay_sandbox_refresh_token = Column("ebay_sandbox_refresh_token", Text, nullable=True)
    ebay_sandbox_token_expires_at = Column(DateTime, nullable=True)
    
    sync_logs = relationship("SyncLog", back_populates="user")
    sync_event_logs = relationship("SyncEventLog", back_populates="user")
    
    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_role', 'role'),
    )

    # ------------------------------------------------------------------
    # Encrypted eBay token accessors (per-user legacy tokens)
    # ------------------------------------------------------------------
    @property
    def ebay_access_token(self) -> str | None:
        from app.utils import crypto

        raw = self._ebay_access_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @ebay_access_token.setter
    def ebay_access_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._ebay_access_token = None
        else:
            self._ebay_access_token = crypto.encrypt(value)

    @property
    def ebay_refresh_token(self) -> str | None:
        from app.utils import crypto

        raw = self._ebay_refresh_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @ebay_refresh_token.setter
    def ebay_refresh_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._ebay_refresh_token = None
        else:
            self._ebay_refresh_token = crypto.encrypt(value)

    @property
    def ebay_sandbox_access_token(self) -> str | None:
        from app.utils import crypto

        raw = self._ebay_sandbox_access_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @ebay_sandbox_access_token.setter
    def ebay_sandbox_access_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._ebay_sandbox_access_token = None
        else:
            self._ebay_sandbox_access_token = crypto.encrypt(value)

    @property
    def ebay_sandbox_refresh_token(self) -> str | None:
        from app.utils import crypto

        raw = self._ebay_sandbox_refresh_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @ebay_sandbox_refresh_token.setter
    def ebay_sandbox_refresh_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._ebay_sandbox_refresh_token = None
        else:
            self._ebay_sandbox_refresh_token = crypto.encrypt(value)


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


class SqInternalCategory(Base):
    """Dictionary of internal SQ categories (legacy Internal Category)."""

    __tablename__ = "sq_internal_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    label = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=True)


class SqShippingGroup(Base):
    """Dictionary of SQ shipping groups used by SQ catalog and listings."""

    __tablename__ = "sq_shipping_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    label = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=True)


class ItemCondition(Base):
    """Dictionary of item conditions for SQ catalog (maps to legacy ConditionID)."""

    __tablename__ = "item_conditions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    label = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=True)


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

    # Optional link to parts_detail row used by the eBay listing worker.
    # This is populated when listings are committed from the ListingPage and
    # allows Inventory status changes to keep PartsDetail.status_sku in sync.
    parts_detail_id = Column(Integer, nullable=True, index=True)
    
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


class PartsDetailStatus(str, enum.Enum):
    """High-level business status for parts_detail.sku/listing lifecycle.

    This is a thin semantic layer over the legacy numeric StatusSKU codes from
    the historical MSSQL schema. We intentionally keep the enum small and map
    concrete numeric codes in application logic where needed.
    """

    AWAITING_MODERATION = "AwaitingModeration"
    CHECKED = "Checked"
    LISTED_ACTIVE = "ListedActive"
    ENDED = "Ended"
    CANCELLED = "Cancelled"
    PUBLISH_ERROR = "PublishError"


class PartsDetail(Base):
    """Supabase/Postgres equivalent of legacy dbo.tbl_parts_detail.

    Only the core columns required by the first implementation of the eBay
    listing worker are modelled here. Additional legacy columns can be added
    incrementally as we migrate more behaviour.
    """

    __tablename__ = "parts_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identity & warehouse
    sku = Column(String(100), nullable=True, index=True)
    sku2 = Column(String(100), nullable=True)
    override_sku = Column(String(100), nullable=True)
    storage = Column(String(100), nullable=True, index=True)
    alt_storage = Column(String(100), nullable=True)
    storage_alias = Column(String(100), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)

    # eBay account & linkage
    item_id = Column(String(100), nullable=True, index=True)
    ebay_id = Column(String(64), nullable=True, index=True)  # internal account/site id
    username = Column(String(100), nullable=True, index=True)  # eBay username
    global_ebay_id_for_relist = Column(String(64), nullable=True)
    global_ebay_id_for_relist_flag = Column(Boolean, nullable=True)

    # Status fields (stored as string; PartsDetailStatus is a semantic helper enum)
    status_sku = Column(String(32), nullable=True, index=True)
    listing_status = Column(String(50), nullable=True, index=True)
    status_updated_at = Column(DateTime(timezone=True), nullable=True)
    status_updated_by = Column(String(100), nullable=True)
    listing_status_updated_at = Column(DateTime(timezone=True), nullable=True)
    listing_status_updated_by = Column(String(100), nullable=True)

    # Listing lifetime
    listing_start_time = Column(DateTime(timezone=True), nullable=True)
    listing_end_time = Column(DateTime(timezone=True), nullable=True)
    listing_time_updated = Column(DateTime(timezone=True), nullable=True)
    item_listed_at = Column(DateTime(timezone=True), nullable=True)

    # Prices & overrides
    override_price = Column(Numeric(14, 2), nullable=True)
    price_to_change = Column(Numeric(14, 2), nullable=True)
    price_to_change_one_time = Column(Numeric(14, 2), nullable=True)
    override_price_flag = Column(Boolean, nullable=True)
    price_to_change_flag = Column(Boolean, nullable=True)
    price_to_change_one_time_flag = Column(Boolean, nullable=True)

    # Best Offer
    best_offer_enabled_flag = Column(Boolean, nullable=True)
    best_offer_auto_accept_price_flag = Column(Boolean, nullable=True)
    best_offer_auto_accept_price_value = Column(Numeric(14, 2), nullable=True)
    best_offer_auto_accept_price_percent = Column(Numeric(5, 2), nullable=True)
    best_offer_min_price_flag = Column(Boolean, nullable=True)
    best_offer_min_price_value = Column(Numeric(14, 2), nullable=True)
    best_offer_min_price_percent = Column(Numeric(5, 2), nullable=True)
    best_offer_mode = Column(String(20), nullable=True)
    best_offer_to_change_flag = Column(Boolean, nullable=True)
    active_best_offer_flag = Column(Boolean, nullable=True)
    active_best_offer_manual_flag = Column(Boolean, nullable=True)

    # Title, description, pictures
    override_title = Column(Text, nullable=True)
    override_description = Column(Text, nullable=True)
    override_condition_id = Column(Integer, nullable=True)
    condition_description_to_change = Column(Text, nullable=True)
    override_pic_url_1 = Column(Text, nullable=True)
    override_pic_url_2 = Column(Text, nullable=True)
    override_pic_url_3 = Column(Text, nullable=True)
    override_pic_url_4 = Column(Text, nullable=True)
    override_pic_url_5 = Column(Text, nullable=True)
    override_pic_url_6 = Column(Text, nullable=True)
    override_pic_url_7 = Column(Text, nullable=True)
    override_pic_url_8 = Column(Text, nullable=True)
    override_pic_url_9 = Column(Text, nullable=True)
    override_pic_url_10 = Column(Text, nullable=True)
    override_pic_url_11 = Column(Text, nullable=True)
    override_pic_url_12 = Column(Text, nullable=True)

    # eBay API ACK / errors
    verify_ack = Column(String(20), nullable=True)
    verify_timestamp = Column(DateTime(timezone=True), nullable=True)
    verify_error = Column(Text, nullable=True)
    add_ack = Column(String(20), nullable=True)
    add_timestamp = Column(DateTime(timezone=True), nullable=True)
    add_error = Column(Text, nullable=True)
    revise_ack = Column(String(20), nullable=True)
    revise_timestamp = Column(DateTime(timezone=True), nullable=True)
    revise_error = Column(Text, nullable=True)

    # Batch / queue flags
    batch_error_flag = Column(Boolean, nullable=True, index=True)
    batch_error_message = Column(JSONB, nullable=True)
    batch_success_flag = Column(Boolean, nullable=True, index=True)
    batch_success_message = Column(JSONB, nullable=True)
    mark_as_listed_queue_flag = Column(Boolean, nullable=True, index=True)
    mark_as_listed_queue_updated_at = Column(DateTime(timezone=True), nullable=True)
    mark_as_listed_queue_updated_by = Column(String(100), nullable=True)
    listing_price_batch_flag = Column(Boolean, nullable=True)
    cancel_listing_queue_flag = Column(Boolean, nullable=True)
    cancel_listing_queue_flag_updated_at = Column(DateTime(timezone=True), nullable=True)
    cancel_listing_queue_flag_updated_by = Column(String(100), nullable=True)
    relist_listing_queue_flag = Column(Boolean, nullable=True)
    relist_listing_queue_flag_updated_at = Column(DateTime(timezone=True), nullable=True)
    relist_listing_queue_flag_updated_by = Column(String(100), nullable=True)
    freeze_listing_queue_flag = Column(Boolean, nullable=True)

    # Event flags
    relist_flag = Column(Boolean, nullable=True)
    relist_quantity = Column(Integer, nullable=True)
    relist_listing_flag = Column(Boolean, nullable=True)
    relist_listing_flag_updated_at = Column(DateTime(timezone=True), nullable=True)
    relist_listing_flag_updated_by = Column(String(100), nullable=True)
    cancel_listing_flag = Column(Boolean, nullable=True)
    cancel_listing_status_sku = Column(String(50), nullable=True)
    cancel_listing_interface = Column(String(50), nullable=True)
    freeze_listing_flag = Column(Boolean, nullable=True)
    phantom_cancel_listing_flag = Column(Boolean, nullable=True)
    ended_for_relist_flag = Column(Boolean, nullable=True)
    just_sold_flag = Column(Boolean, nullable=True)
    return_flag = Column(Boolean, nullable=True)
    loss_flag = Column(Boolean, nullable=True)

    # Audit
    # Use server_default=func.now() instead of datetime.utcnow function object to
    # satisfy SQLAlchemy 2.x ArgumentError expectations.
    record_created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    record_created_by = Column(String(100), nullable=True)
    record_updated_at = Column(DateTime(timezone=True), nullable=True)
    record_updated_by = Column(String(100), nullable=True)

    logs = relationship("PartsDetailLog", back_populates="part_detail", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_parts_detail_sku", "sku"),
        Index("idx_parts_detail_item_id", "item_id"),
        Index("idx_parts_detail_status_sku", "status_sku"),
        Index("idx_parts_detail_listing_status", "listing_status"),
        Index("idx_parts_detail_username", "username"),
        Index("idx_parts_detail_ebay_id", "ebay_id"),
    )


class PartsDetailLog(Base):
    """High-level audit log for PartsDetail changes and worker events."""

    __tablename__ = "parts_detail_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_detail_id = Column(Integer, ForeignKey("parts_detail.id", ondelete="CASCADE"), nullable=False, index=True)

    # Linkage / snapshot identifiers
    sku = Column(String(100), nullable=True, index=True)
    model_id = Column(Integer, nullable=True)

    # Product snapshot
    part = Column(Text, nullable=True)
    price = Column(Numeric(14, 2), nullable=True)
    previous_price = Column(Numeric(14, 2), nullable=True)
    price_updated_at = Column(DateTime(timezone=True), nullable=True)
    market = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    shipping_type = Column(String(50), nullable=True)
    shipping_group = Column(String(50), nullable=True)
    condition_id = Column(Integer, nullable=True)
    pic_url_1 = Column(Text, nullable=True)
    pic_url_2 = Column(Text, nullable=True)
    pic_url_3 = Column(Text, nullable=True)
    pic_url_4 = Column(Text, nullable=True)
    pic_url_5 = Column(Text, nullable=True)
    pic_url_6 = Column(Text, nullable=True)
    pic_url_7 = Column(Text, nullable=True)
    pic_url_8 = Column(Text, nullable=True)
    pic_url_9 = Column(Text, nullable=True)
    pic_url_10 = Column(Text, nullable=True)
    pic_url_11 = Column(Text, nullable=True)
    pic_url_12 = Column(Text, nullable=True)
    weight = Column(Numeric(12, 3), nullable=True)
    part_number = Column(String(100), nullable=True)

    # Flags & statuses
    alert_flag = Column(Boolean, nullable=True)
    alert_message = Column(Text, nullable=True)
    record_status = Column(String(50), nullable=True)
    record_status_flag = Column(Boolean, nullable=True)
    checked_status = Column(String(50), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    checked_by = Column(String(100), nullable=True)
    one_time_auction = Column(Boolean, nullable=True)

    # Audit
    record_created_at = Column(DateTime(timezone=True), nullable=True)
    record_created_by = Column(String(100), nullable=True)
    record_updated_at = Column(DateTime(timezone=True), nullable=True)
    record_updated_by = Column(String(100), nullable=True)
    log_created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    log_created_by = Column(String(100), nullable=True)

    part_detail = relationship("PartsDetail", back_populates="logs")

    __table_args__ = (
        Index("idx_parts_detail_log_part_detail_id", "part_detail_id"),
        Index("idx_parts_detail_log_sku", "sku"),
        Index("idx_parts_detail_log_checked_status", "checked_status"),
    )


# Attempt reflection of the legacy Supabase inventory table at import time,
# but never crash the app if it is missing in the current environment or the
# database is temporarily unreachable.
try:
    tbl_parts_inventory_table = Table(
        "tbl_parts_inventory",  # REAL table name, do not change
        Base.metadata,
        autoload_with=engine,
    )
    # Inspect primary key constraint; this table currently has none defined
    # at the database level, so we will treat the real "ID" column as the
    # logical primary key for ORM purposes.
    inspector = inspect(engine)
    pk_info = inspector.get_pk_constraint(
        tbl_parts_inventory_table.name,
        schema=tbl_parts_inventory_table.schema,
    )
    pk_cols = list(pk_info.get("constrained_columns") or [])
    if not pk_cols and "ID" in tbl_parts_inventory_table.c:
        pk_cols = ["ID"]
except (NoSuchTableError, OperationalError) as exc:
    logger.warning(
        "tbl_parts_inventory reflection failed (%s); TblPartsInventory will be abstract in this environment",
        type(exc).__name__,
    )
    tbl_parts_inventory_table = None
    pk_cols = []


if tbl_parts_inventory_table is not None and pk_cols:
    class TblPartsInventory(Base):
        """Supabase parts inventory table mapped to tbl_parts_inventory.

        Uses the real numeric "ID" column (or DB-defined PK) as the mapper
        primary key so SQLAlchemy can assemble a valid identity map even
        though the legacy table lacks an explicit PRIMARY KEY constraint.
        """

        __table__ = tbl_parts_inventory_table
        __mapper_args__ = {
            "primary_key": tuple(tbl_parts_inventory_table.c[col] for col in pk_cols),
        }
else:
    class TblPartsInventory(Base):
        """Abstract placeholder when tbl_parts_inventory does not exist or lacks a usable PK.

        Marked abstract so SQLAlchemy does not try to map a non-existent or
        unusable table and the application can still start cleanly.
        """

        __abstract__ = True


# Optional reflection of the legacy models dictionary table used for the
# SKU create/edit form typeahead (tbl_parts_models). Missing tables and
# transient connection errors are tolerated so that environments without the
# legacy schema still boot cleanly.
try:
    tbl_parts_models_table = Table(
        "tbl_parts_models",  # REAL table name provided by legacy system
        Base.metadata,
        autoload_with=engine,
    )
except (NoSuchTableError, OperationalError) as exc:
    logger.warning(
        "tbl_parts_models reflection failed (%s); model search endpoint will return an empty result set",
        type(exc).__name__,
    )
    tbl_parts_models_table = None



if tbl_parts_models_table is not None:
    class TblPartsModels(Base):
        __table__ = tbl_parts_models_table
else:
    class TblPartsModels(Base):
        __abstract__ = True


# Optional reflection of legacy internal categories table used for the
# Internal category dropdown when available (tbl_parts_category). Missing
# tables and transient connection errors are tolerated.
try:
    tbl_parts_category_table = Table(
        "tbl_parts_category",  # REAL table name in Postgres
        Base.metadata,
        autoload_with=engine,
    )
except (NoSuchTableError, OperationalError) as exc:
    logger.warning(
        "tbl_parts_category reflection failed (%s); falling back to sq_internal_categories for internal category list",
        type(exc).__name__,
    )
    tbl_parts_category_table = None


class SqItem(Base):
    """SQ catalog item mapped to the canonical `SKU_catalog` table.

    NOTE: In the Railway/Supabase environment the physical table name
    is mixed-case `"SKU_catalog"` (created with quotes). Postgres
    treats this as case-sensitive, so the ORM must use the exact
    quoted name. By mapping :class:`SqItem` to `SKU_catalog`, all
    existing SKU grid and LISTING code will hit that table instead of
    the old, non-existent `sq_items` table.
    """

    # Mixed-case name ensures SQLAlchemy emits it as a quoted identifier
    # so that Postgres resolves it to the correct relation.
    __tablename__ = "SKU_catalog"

    # Core identifiers / mapping to legacy MSSQL
    # Primary key is stored in legacy column name "ID" on the SKU_catalog table.
    id = Column("ID", BigInteger, primary_key=True, autoincrement=True)  # [ID]
    part_id = Column("Part_ID", BigInteger, nullable=True)  # [Part_ID]
    sku = Column("SKU", Numeric(18, 0), nullable=True)  # [SKU]
    sku2 = Column("SKU2", Text, nullable=True)  # [SKU2]
    # Legacy schema stores only the numeric Model_ID on SKU_catalog.
    # The human-readable model label lives in tbl_parts_models and is
    # surfaced via higher-level joins; there is no "Model" text column
    # on SKU_catalog itself.
    model_id = Column("Model_ID", BigInteger, nullable=True)  # [Model_ID]
    part = Column("Part", Text, nullable=True)  # [Part] – legacy text field used as logical "title"

    # Pricing
    price = Column("Price", Numeric(12, 2), nullable=True)  # [Price]
    previous_price = Column("PreviousPrice", Numeric(12, 2), nullable=True)  # [PreviousPrice]
    brutto = Column("Brutto", Numeric(12, 2), nullable=True)  # [Brutto]
    price_updated = Column("Price_updated", DateTime(timezone=True), nullable=True)  # [Price_updated]

    # Market & category
    market = Column("Market", Text, nullable=True)  # [Market]
    use_ebay_id = Column("UseEbayID", Text, nullable=True)  # [UseEbayID]
    category = Column("Category", Numeric, nullable=True)  # [Category]
    description = Column("Description", Text, nullable=True)  # [Description]

    # Shipping
    shipping_type = Column("ShippingType", Text, nullable=True)  # [ShippingType]
    shipping_group = Column("ShippingGroup", Integer, nullable=True)  # [ShippingGroup]
    shipping_group_previous = Column("ShippingGroupPrevious", Numeric, nullable=True)  # [ShippingGroupPrevious]
    shipping_group_change_state = Column("ShippingGroupChangeState", Integer, nullable=True)  # [ShippingGroupChangeState]
    shipping_group_change_state_updated = Column("ShippingGroupChangeState_updated", DateTime(timezone=True), nullable=True)  # [ShippingGroupChangeState_updated]
    shipping_group_change_state_updated_by = Column("ShippingGroupChangeState_updated_by", Text, nullable=True)  # [ShippingGroupChangeState_updated_by]

    # Condition
    condition_id = Column("ConditionID", Integer, nullable=True)  # [ConditionID] → item_conditions.id
    manual_condition_value_flag = Column("ManualConditionValueFlag", Boolean, nullable=True)  # [ManualConditionValueFlag]

    # Images
    pic_url1 = Column("PicURL1", Text, nullable=True)  # [PicURL1]
    pic_url2 = Column("PicURL2", Text, nullable=True)
    pic_url3 = Column("PicURL3", Text, nullable=True)
    pic_url4 = Column("PicURL4", Text, nullable=True)
    pic_url5 = Column("PicURL5", Text, nullable=True)
    pic_url6 = Column("PicURL6", Text, nullable=True)
    pic_url7 = Column("PicURL7", Text, nullable=True)
    pic_url8 = Column("PicURL8", Text, nullable=True)
    pic_url9 = Column("PicURL9", Text, nullable=True)
    pic_url10 = Column("PicURL10", Text, nullable=True)
    pic_url11 = Column("PicURL11", Text, nullable=True)
    pic_url12 = Column("PicURL12", Text, nullable=True)

    # Physical properties
    weight = Column("Weight", Numeric(12, 3), nullable=True)  # [Weight]
    weight_major = Column("WeightMajor", Numeric(12, 3), nullable=True)  # [WeightMajor]
    weight_minor = Column("WeightMinor", Numeric(12, 3), nullable=True)  # [WeightMinor]
    package_depth = Column("PackageDepth", Numeric(12, 2), nullable=True)  # [PackageDepth]
    package_length = Column("PackageLength", Numeric(12, 2), nullable=True)  # [PackageLength]
    package_width = Column("PackageWidth", Numeric(12, 2), nullable=True)  # [PackageWidth]
    size = Column("Size", Numeric, nullable=True)  # [Size]
    unit = Column("Unit", Text, nullable=True)  # [Unit]

    # Identification codes
    part_number = Column("Part_Number", Text, nullable=True)  # [Part_Number]
    mpn = Column("MPN", Text, nullable=True)  # [MPN]
    upc = Column("UPC", Text, nullable=True)  # [UPC]
    color_flag = Column("ColorFlag", Boolean, nullable=True)  # [ColorFlag]
    color_value = Column("ColorValue", Text, nullable=True)  # [ColorValue]
    epid_flag = Column("EPIDFlag", Boolean, nullable=True)  # [EPIDFlag]
    epid_value = Column("EPIDValue", Text, nullable=True)  # [EPIDValue]

    # Grades & packaging
    item_grade_id = Column("ItemGradeID", Numeric, nullable=True)  # [ItemGradeID]
    basic_package_id = Column("BasicPackageID", Numeric, nullable=True)  # [BasicPackageID]

    # Alert & status
    alert_flag = Column("AlertFlag", Boolean, nullable=True)  # [AlertFlag]
    alert_message = Column("AlertMessage", Text, nullable=True)  # [AlertMessage]
    record_status = Column("RecordStatus", Numeric, nullable=True)  # [RecordStatus]
    record_status_flag = Column("RecordStatusFlag", Boolean, nullable=True)  # [RecordStatusFlag]
    checked_status = Column("CheckedStatus", Boolean, nullable=True)  # [CheckedStatus]
    checked = Column("Checked", DateTime(timezone=True), nullable=True)  # [Checked]
    checked_by = Column("CheckedBy", Text, nullable=True)  # [CheckedBy]
    one_time_auction = Column("OneTimeAuction", Boolean, nullable=True)  # [OneTimeAuction]

    # Audit fields
    record_created_by = Column("record_created_by", Text, nullable=True)  # [record_created_by]
    record_created = Column("record_created", DateTime(timezone=True), nullable=True)  # [record_created]
    record_updated_by = Column("record_updated_by", Text, nullable=True)  # [record_updated_by]
    record_updated = Column("record_updated", DateTime(timezone=True), nullable=True)  # [record_updated]
    oc_export_date = Column("oc_export_date", DateTime(timezone=True), nullable=True)  # [oc_export_date]
    oc_market_export_date = Column("oc_market_export_date", DateTime(timezone=True), nullable=True)  # [oc_market_export_date]

    # Templates & listing metadata
    custom_template_flag = Column("CustomTemplateFlag", Boolean, nullable=True)  # [CustomTemplateFlag]
    custom_template_description = Column("CustomTemplateDescription", Text, nullable=True)  # [CustomTemplateDescription]
    condition_description = Column("ConditionDescription", Text, nullable=True)  # [ConditionDescription]
    domestic_only_flag = Column("DomesticOnlyFlag", Boolean, nullable=True)  # [DomesticOnlyFlag]
    external_category_flag = Column("ExternalCategoryFlag", Boolean, nullable=True)  # [ExternalCategoryFlag]
    external_category_id = Column("ExternalCategoryID", Numeric, nullable=True)  # [ExternalCategoryID]
    external_category_name = Column("ExternalCategoryName", Text, nullable=True)  # [ExternalCategoryName]
    listing_type = Column("ListingType", Text, nullable=True)  # [ListingType]
    listing_duration = Column("ListingDuration", Text, nullable=True)  # [ListingDuration]
    listing_duration_in_days = Column("ListingDurationInDays", Numeric, nullable=True)  # [ListingDurationInDays]
    use_standard_template_for_external_category_flag = Column("UseStandardTemplateForExternalCategoryFlag", Boolean, nullable=True)  # [UseStandardTemplateForExternalCategoryFlag]
    use_ebay_motors_site_flag = Column("UseEbayMotorsSiteFlag", Boolean, nullable=True)  # [UseEbayMotorsSiteFlag]
    site_id = Column("SiteID", Numeric, nullable=True)  # [SiteID] – e.g. EBAY-US

    # Clone SKU metadata
    clone_sku_flag = Column("CloneSKUFlag", Boolean, nullable=True)  # [CloneSKUFlag]
    clone_sku_updated = Column("CloneSKU_updated", DateTime(timezone=True), nullable=True)  # [CloneSKU_updated]
    clone_sku_updated_by = Column("CloneSKU_updated_by", Text, nullable=True)  # [CloneSKU_updated_by]

    # Synthetic / convenience attributes that do not correspond 1:1 to legacy
    # SKU_catalog columns.
    #
    # - ``title`` is exposed as a property alias over the legacy ``Part``
    #   column so the modern UI can talk in terms of "Title" while the
    #   database continues to use ``Part`` as the canonical text field.
    # - ``model`` is populated by higher-level code (joins to
    #   ``tbl_parts_models``) and is *not* stored on SKU_catalog; only
    #   ``model_id`` is persisted.
    model = None
    brand = None
    warehouse_id = None
    storage_alias = None

    warehouse = None

    @property
    def title(self):  # type: ignore[override]
        return self.part

    @title.setter
    def title(self, value):  # type: ignore[override]
        self.part = value

    # Legacy SKU_catalog already has its own indexes at the database level.
    # Declaring ORM Index objects with lower-case logical names (e.g. 'sku')
    # caused ConstraintColumnNotFoundError when loading models. We omit
    # __table_args__ here to avoid that; performance stays acceptable.
    __table_args__ = ()


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


class EbayReturn(Base):
    """Post-Order returns table (ebay_returns).

    This table stores normalized Post-Order return records per user/account,
    mirroring the Postgres schema created by the Alembic migration
    `ebay_returns_20251201`.
    """

    __tablename__ = "ebay_returns"

    # В реальной схеме первичный ключ составной: (return_id, user_id).
    # Модель должна точно соответствовать БД, поэтому не вводим
    # искусственный "id" и отмечаем оба поля как primary_key.
    return_id = Column(String(100), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)

    ebay_account_id = Column(String(36), ForeignKey("ebay_accounts.id"), nullable=True, index=True)
    ebay_user_id = Column(String(64), nullable=True, index=True)

    order_id = Column(String(100), nullable=True, index=True)
    item_id = Column(String(100), nullable=True)
    transaction_id = Column(String(100), nullable=True)

    return_state = Column(String(50), nullable=True, index=True)
    return_type = Column(String(50), nullable=True)
    reason = Column(Text, nullable=True)

    buyer_username = Column(Text, nullable=True)
    seller_username = Column(Text, nullable=True)

    total_amount_value = Column(Numeric(12, 2), nullable=True)
    total_amount_currency = Column(String(10), nullable=True)

    creation_date = Column(DateTime(timezone=True), nullable=True, index=True)
    last_modified_date = Column(DateTime(timezone=True), nullable=True, index=True)
    closed_date = Column(DateTime(timezone=True), nullable=True)

    raw_json = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Composite natural key used for upserts and deduplication.
        Index("idx_ebay_returns_account_return", "ebay_account_id", "return_id", unique=True),
        Index("idx_ebay_returns_state_last_modified", "ebay_account_id", "return_state", "last_modified_date"),
        Index("idx_ebay_returns_creation_date", "ebay_account_id", "creation_date"),
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
    # Optional label for the logical source of the call, e.g. "debug", "scheduled", "admin".
    source = Column(String(32), nullable=True, index=True)

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
        Index('idx_ebay_connect_logs_source', 'source'),
    )


class SecurityEvent(Base):
    """Append-only log of security-relevant events (auth, settings, alerts).

    Examples of event_type values:
    - login_success
    - login_failed
    - login_blocked
    - session_invalidated
    - settings_changed
    - security_alert
    """

    __tablename__ = "security_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    user_id = Column(String(36), ForeignKey('users.id'), nullable=True, index=True)
    ip_address = Column(String(64), nullable=True, index=True)
    user_agent = Column(Text, nullable=True)

    event_type = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Flexible metadata payload stored in the "metadata" column; must never contain raw passwords or tokens.
    metadata_json = Column("metadata", JSONB, nullable=True)

    user = relationship("User", backref="security_events")

    __table_args__ = (
        Index('idx_security_events_user_time', 'user_id', 'created_at'),
        Index('idx_security_events_ip_time', 'ip_address', 'created_at'),
    )


class LoginAttempt(Base):
    """Canonical record of each login attempt and block decision.

    Rows are written for both successful and failed login attempts, and can
    be queried by email+IP to compute progressive delays.
    """

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Identifier used at login time; may or may not correspond to a real user.
    email = Column(String(255), nullable=False, index=True)

    # Optional linkage to the canonical user row when available.
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True, index=True)

    ip_address = Column(String(64), nullable=True, index=True)
    user_agent = Column(Text, nullable=True)

    success = Column(Boolean, nullable=False, default=False, index=True)
    reason = Column(String(100), nullable=True)

    # Whether a block was applied as a result of this attempt and until when.
    block_applied = Column(Boolean, nullable=False, default=False)
    block_until = Column(DateTime(timezone=True), nullable=True)

    metadata_json = Column("metadata", JSONB, nullable=True)

    user = relationship("User", backref="login_attempts")

    __table_args__ = (
        Index('idx_login_attempts_email_ip_time', 'email', 'ip_address', 'created_at'),
    )


class SecuritySettings(Base):
    """Singleton row storing brute-force and session security parameters.

    The application should treat this table as a single-record configuration
    store, loading row id=1 (or creating it with defaults when absent).
    """

    __tablename__ = "security_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Brute-force / login protections
    max_failed_attempts = Column(Integer, nullable=False, default=3)
    initial_block_minutes = Column(Integer, nullable=False, default=1)
    progressive_delay_step_minutes = Column(Integer, nullable=False, default=2)
    max_delay_minutes = Column(Integer, nullable=False, default=30)

    enable_captcha = Column(Boolean, nullable=False, default=False)
    captcha_after_failures = Column(Integer, nullable=False, default=3)

    # Session lifetime and idle timeout (applied to JWT expiry and middleware).
    session_ttl_minutes = Column(Integer, nullable=False, default=60 * 12)  # 12 hours
    session_idle_timeout_minutes = Column(Integer, nullable=False, default=60)  # 1 hour

    # Simple alert thresholds; used by future anomaly detection/alerting.
    bruteforce_alert_threshold_per_ip = Column(Integer, nullable=False, default=50)
    bruteforce_alert_threshold_per_user = Column(Integer, nullable=False, default=50)

    alert_email_enabled = Column(Boolean, nullable=False, default=False)
    alert_channel = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_security_settings_updated_at', 'updated_at'),
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
    # Optional visual theme + layout options (density, font size, color scheme, etc.)
    # Stored as a JSON object so backend and frontend can evolve independently.
    theme = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_user_grid_layouts_user_grid', 'user_id', 'grid_key', unique=True),
    )


class UiTweakSettings(Base):
    """Global UI tweak settings persisted as a single JSON document.

    This stores the UITweakSettings payload used by the frontend (fontScale,
    navScale, gridDensity, nav colors, typography, colors, controls, etc.) so
    that admin-chosen values apply to all users and browsers.
    """

    __tablename__ = "ui_tweak_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Arbitrary JSON payload shaped like the frontend UITweakSettings model.
    settings = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AiRule(Base):
    """Persisted AI analytics rule, typically a reusable SQL condition fragment.

    These rules are created from natural-language descriptions in the admin
    AI Rules UI and later reused by analytics and monitoring workers (e.g.
    "good computer" profitability profiles).
    """

    __tablename__ = "ai_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False)
    # Raw SQL condition fragment or full WHERE clause (read-only, validated at use).
    rule_sql = Column(Text, nullable=False)
    # Optional free-form description or original natural-language prompt.
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)


class AiQueryLog(Base):
    """Append-only log of AI-powered admin analytics queries.

    Each row captures the natural-language prompt, the generated SQL, and the
    number of rows returned so we can audit and debug the AI Query Engine.
    """

    __tablename__ = "ai_query_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    sql = Column(Text, nullable=False)
    row_count = Column(Integer, nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class AiEbayCandidate(Base):
    """Candidate eBay listing discovered by the monitoring worker.

    Each row represents a potentially profitable listing for a given model
    discovered via the eBay Browse/Search API.
    """

    __tablename__ = "ai_ebay_candidates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    ebay_item_id = Column(Text, nullable=False, unique=True)
    model_id = Column(Text, nullable=False, index=True)

    title = Column(Text, nullable=True)
    price = Column(Numeric(14, 2), nullable=True)
    shipping = Column(Numeric(14, 2), nullable=True)
    condition = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    predicted_profit = Column(Numeric(14, 2), nullable=True)
    roi = Column(Numeric(10, 4), nullable=True)

    matched_rule = Column(Boolean, nullable=True)
    rule_name = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_ai_ebay_candidates_model_id", "model_id"),
    )


class AiEbayAction(Base):
    """Planned auto-offer / auto-buy action for a discovered eBay candidate.

    This table is populated by the auto-offer/auto-buy worker and can be
    reviewed in the admin UI before enabling live execution.
    """

    __tablename__ = "ai_ebay_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    ebay_item_id = Column(Text, nullable=False)
    model_id = Column(Text, nullable=False, index=True)

    # 'offer' | 'buy_now'
    action_type = Column(Text, nullable=False)

    # Planned amount we intend to pay or offer (same currency as original_price).
    offer_amount = Column(Numeric(14, 2), nullable=True)
    original_price = Column(Numeric(14, 2), nullable=True)
    shipping = Column(Numeric(14, 2), nullable=True)

    predicted_profit = Column(Numeric(14, 2), nullable=True)
    roi = Column(Numeric(10, 4), nullable=True)

    rule_name = Column(Text, nullable=True)

    # 'draft' | 'ready' | 'executed' | 'failed'
    status = Column(Text, nullable=False, default="draft")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_ai_ebay_actions_model_id", "model_id"),
        Index("uq_ai_ebay_actions_item_type", "ebay_item_id", "action_type", unique=True),
    )


class IntegrationProvider(Base):
    """Catalog entry for an external integration provider (Gmail, Slack, etc.)."""

    __tablename__ = "integrations_providers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(64), nullable=False, unique=True)
    name = Column(Text, nullable=False)
    auth_type = Column(String(32), nullable=False)
    default_scopes = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    accounts = relationship("IntegrationAccount", back_populates="provider")


class IntegrationAccount(Base):
    """Concrete connected account for a given provider and owner.

    Example: Filipp's main Gmail account, a client's Slack workspace, etc.
    """

    __tablename__ = "integrations_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    provider_id = Column(String(36), ForeignKey("integrations_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    external_account_id = Column(Text, nullable=False)  # e.g. email for Gmail
    display_name = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="active", index=True)

    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    provider = relationship("IntegrationProvider", back_populates="accounts")
    owner = relationship("User")
    credentials = relationship("IntegrationCredentials", back_populates="account", uselist=False)
    email_messages = relationship("EmailMessage", back_populates="integration_account")
    training_pairs = relationship("AiEmailTrainingPair", back_populates="integration_account")


class IntegrationCredentials(Base):
    """Encrypted credentials for a single IntegrationAccount.

    Access and refresh tokens are stored encrypted at rest using the shared
    crypto helper (AES-GCM derived from the application secret key).
    """

    __tablename__ = "integrations_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    integration_account_id = Column(
        String(36),
        ForeignKey("integrations_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    _access_token = Column("access_token", Text, nullable=True)
    _refresh_token = Column("refresh_token", Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    account = relationship("IntegrationAccount", back_populates="credentials")

    # ------------------------------------------------------------------
    # Encrypted token accessors
    # ------------------------------------------------------------------
    @property
    def access_token(self) -> str | None:
        from app.utils import crypto

        raw = self._access_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @access_token.setter
    def access_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._access_token = None
        else:
            self._access_token = crypto.encrypt(value)

    @property
    def refresh_token(self) -> str | None:
        from app.utils import crypto

        raw = self._refresh_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._refresh_token = None
        else:
            self._refresh_token = crypto.encrypt(value)


class EmailMessage(Base):
    """Normalized email message fetched from an external provider.

    This table is provider-agnostic; Gmail is simply the first concrete
    implementation via the Integrations module.
    """

    __tablename__ = "emails_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    integration_account_id = Column(
        String(36),
        ForeignKey("integrations_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    external_id = Column(Text, nullable=False)
    thread_id = Column(Text, nullable=True, index=True)

    direction = Column(String(16), nullable=False)  # incoming | outgoing

    from_address = Column(Text, nullable=True)
    to_addresses = Column(JSONB, nullable=True)
    cc_addresses = Column(JSONB, nullable=True)
    bcc_addresses = Column(JSONB, nullable=True)

    subject = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True, index=True)
    raw_headers = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    integration_account = relationship("IntegrationAccount", back_populates="email_messages")
    client_pairs = relationship(
        "AiEmailTrainingPair",
        back_populates="client_message",
        foreign_keys="AiEmailTrainingPair.client_message_id",
    )
    reply_pairs = relationship(
        "AiEmailTrainingPair",
        back_populates="our_reply_message",
        foreign_keys="AiEmailTrainingPair.our_reply_message_id",
    )

    __table_args__ = (
        Index(
            "uq_emails_messages_account_external_id",
            "integration_account_id",
            "external_id",
            unique=True,
        ),
    )


class AiEmailTrainingPair(Base):
    """Paired client question and our reply extracted from email threads.

    These rows power the AI email training dataset once approved in the
    admin UI.
    """

    __tablename__ = "ai_training_pairs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    integration_account_id = Column(
        String(36),
        ForeignKey("integrations_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    thread_id = Column(Text, nullable=True, index=True)

    client_message_id = Column(
        String(36),
        ForeignKey("emails_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    our_reply_message_id = Column(
        String(36),
        ForeignKey("emails_messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    client_text = Column(Text, nullable=False)
    our_reply_text = Column(Text, nullable=False)

    status = Column(String(32), nullable=False, default="new", index=True)
    labels = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    integration_account = relationship("IntegrationAccount", back_populates="training_pairs")
    client_message = relationship("EmailMessage", foreign_keys=[client_message_id], back_populates="client_pairs")
    our_reply_message = relationship("EmailMessage", foreign_keys=[our_reply_message_id], back_populates="reply_pairs")


class AiProvider(Base):
    """AI provider configuration, including encrypted API keys (e.g. OpenAI).

    This table starts with a single provider_code="openai" row but is generic
    enough to support additional providers in the future.
    """

    __tablename__ = "ai_providers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    provider_code = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)

    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    _api_key = Column("api_key", Text, nullable=True)
    model_default = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # ------------------------------------------------------------------
    # Encrypted API key accessors
    # ------------------------------------------------------------------
    @property
    def api_key(self) -> str | None:
        from app.utils import crypto

        raw = self._api_key
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._api_key = None
        else:
            self._api_key = crypto.encrypt(value)


class AccountingExpenseCategory(Base):
    __tablename__ = "accounting_expense_category"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AccountingInternalCategory(Base):
    """Internal classification reference table (bank_transaction_category_internal)."""
    __tablename__ = "bank_transaction_category_internal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), nullable=False, unique=True)
    display_name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey('bank_transaction_category_internal.id'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    parent = relationship("AccountingInternalCategory", remote_side=[id])


class AccountingGroup(Base):
    """Accounting group categories (INCOME, COGS, OPEX, etc.)."""
    __tablename__ = "accounting_group"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    color = Column(Text, nullable=True, server_default='#6b7280')
    sort_order = Column(Integer, nullable=False, server_default='0')
    is_active = Column(Boolean, nullable=False, server_default='true')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Note: No relationship to AccountingClassificationCode because we use text-based FK (code)
    # Join manually in queries: db.query(...).filter(AccountingClassificationCode.accounting_group == AccountingGroup.code)


class AccountingClassificationCode(Base):
    """Classification codes for bank transactions (user-manageable)."""
    __tablename__ = "accounting_classification_code"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    accounting_group = Column(Text, nullable=False)  # References AccountingGroup.code (no FK constraint)
    keywords = Column(Text, nullable=True)  # Comma-separated keywords for auto-classification
    sort_order = Column(Integer, nullable=False, server_default='0')
    is_active = Column(Boolean, nullable=False, server_default='true')
    is_system = Column(Boolean, nullable=False, server_default='false')  # System codes can't be deleted
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Note: No relationship to AccountingGroup - use manual joins


class AccountingBankStatement(Base):
    __tablename__ = "accounting_bank_statement"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    bank_name = Column(Text, nullable=False)
    account_last4 = Column(Text, nullable=True)
    currency = Column(Text, nullable=True)
    statement_period_start = Column(Date, nullable=True)
    statement_period_end = Column(Date, nullable=True)
    opening_balance = Column(Numeric(14, 2), nullable=True)
    closing_balance = Column(Numeric(14, 2), nullable=True)
    total_debit = Column(Numeric(14, 2), nullable=True)
    total_credit = Column(Numeric(14, 2), nullable=True)
    status = Column(Text, nullable=False, default="uploaded")
    file_hash = Column(Text, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)  # Made nullable for script imports

    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)

    # Supabase storage info
    supabase_bucket = Column(Text, nullable=True)
    supabase_path = Column(Text, nullable=True)
    
    # Error handling & debugging
    error_message = Column(Text, nullable=True)
    raw_header_json = Column(JSONB, nullable=True)
    raw_openai_response = Column(JSONB, nullable=True)
    
    # Bank Statement v1.0 fields
    raw_json = Column(JSONB, nullable=True)  # Full Bank Statement v1.0 JSON
    statement_hash = Column(Text, nullable=True, index=True)  # For idempotency
    source_type = Column(Text, nullable=True, server_default="MANUAL")  # JSON_UPLOAD, PDF_TD, CSV, XLSX, OPENAI
    bank_code = Column(Text, nullable=True, index=True)  # Short bank code (TD, BOA, CITI)

    __table_args__ = (
        Index('idx_accounting_bank_statement_file_hash', 'file_hash'),
        Index('idx_accounting_bank_statement_stmt_hash', 'statement_hash'),
        Index('idx_accounting_bank_statement_bank_code', 'bank_code'),
    )


class AccountingBankStatementFile(Base):
    __tablename__ = "accounting_bank_statement_file"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bank_statement_id = Column(BigInteger, ForeignKey('accounting_bank_statement.id', ondelete='CASCADE'), nullable=False)
    file_type = Column(Text, nullable=False)
    storage_path = Column(Text, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    uploaded_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=False)


class AccountingBankRow(Base):
    __tablename__ = "accounting_bank_row"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bank_statement_id = Column(BigInteger, ForeignKey('accounting_bank_statement.id', ondelete='CASCADE'), nullable=False)
    row_index = Column(Integer, nullable=True)
    operation_date = Column(Date, nullable=True, index=True)
    posting_date = Column(Date, nullable=True)
    description_raw = Column(Text, nullable=False)
    description_clean = Column(Text, nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    balance_after = Column(Numeric(14, 2), nullable=True)
    currency = Column(Text, nullable=True)
    parsed_status = Column(Text, nullable=False, default="auto_parsed")
    match_status = Column(Text, nullable=False, default="unmatched")
    dedupe_key = Column(Text, nullable=True, index=True)
    
    # Classification (legacy)
    llm_category = Column(Text, nullable=False, server_default="unknown")
    internal_category_id = Column(Integer, ForeignKey('bank_transaction_category_internal.id'), nullable=True)
    internal_category_label = Column(Text, nullable=True)
    
    expense_category_id = Column(BigInteger, ForeignKey('accounting_expense_category.id'), nullable=True)
    
    # Bank Statement v1.0 classification fields
    bank_code = Column(Text, nullable=True, index=True)  # TD, BOA, CITI
    bank_section = Column(Text, nullable=True, index=True)  # ELECTRONIC_DEPOSIT, CHECKS_PAID, etc.
    bank_subtype = Column(Text, nullable=True)  # CCD DEPOSIT, ACH DEBIT, etc.
    direction = Column(Text, nullable=True, index=True)  # CREDIT or DEBIT
    accounting_group = Column(Text, nullable=True, index=True)  # INCOME, COGS, OPERATING_EXPENSE, etc.
    classification = Column(Text, nullable=True, index=True)  # INCOME_EBAY_PAYOUT, etc.
    classification_status = Column(Text, nullable=True, server_default="UNKNOWN", index=True)  # OK, UNKNOWN, ERROR
    check_number = Column(Text, nullable=True)  # Check number if applicable
    raw_transaction_json = Column(JSONB, nullable=True)  # Raw JSON from Bank Statement v1.0
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        Index('idx_accounting_bank_row_dedupe_key', 'dedupe_key'),
        Index('idx_accounting_bank_row_bank_code', 'bank_code'),
        Index('idx_accounting_bank_row_bank_section', 'bank_section'),
        Index('idx_accounting_bank_row_direction', 'direction'),
        Index('idx_accounting_bank_row_accounting_group', 'accounting_group'),
        Index('idx_accounting_bank_row_classification', 'classification'),
        Index('idx_accounting_bank_row_classification_status', 'classification_status'),
    )


class AccountingCashExpense(Base):
    __tablename__ = "accounting_cash_expense"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(Text, nullable=True)
    paid_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    counterparty = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    expense_category_id = Column(BigInteger, ForeignKey('accounting_expense_category.id'), nullable=False)
    storage_id = Column(Text, nullable=True)
    receipt_image_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)


class AccountingTransaction(Base):
    __tablename__ = "accounting_transaction"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    direction = Column(Text, nullable=False)  # 'in' or 'out'
    source_type = Column(Text, nullable=False, index=True)
    source_id = Column(BigInteger, nullable=False)
    bank_row_id = Column(BigInteger, ForeignKey('accounting_bank_row.id'), nullable=True, unique=True)
    account_name = Column(Text, nullable=True)
    account_id = Column(Text, nullable=True)
    counterparty = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    expense_category_id = Column(BigInteger, ForeignKey('accounting_expense_category.id'), nullable=True, index=True)
    subcategory = Column(Text, nullable=True)
    storage_id = Column(Text, nullable=True, index=True)
    linked_object_type = Column(Text, nullable=True)
    linked_object_id = Column(Text, nullable=True)
    is_personal = Column(Boolean, nullable=False, server_default="false")
    is_internal_transfer = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)


class AccountingTransactionLog(Base):
    __tablename__ = "accounting_transaction_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id = Column(BigInteger, ForeignKey('accounting_transaction.id', ondelete='CASCADE'), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    changed_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    field_name = Column(Text, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)


class AccountingBankRule(Base):
    __tablename__ = "accounting_bank_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    pattern_type = Column(Text, nullable=False)  # 'contains', 'regex', 'counterparty', 'llm_label'
    pattern_value = Column(Text, nullable=False)
    expense_category_id = Column(BigInteger, ForeignKey('accounting_expense_category.id'), nullable=False)
    priority = Column(Integer, nullable=False, default=10)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey('users.id'), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_accounting_bank_rule_active_priority', 'is_active', 'priority'),
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


class AccountingBankStatementImportRun(Base):
    """Audit log of each bank statement import attempt."""
    __tablename__ = "bank_statement_import_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_statement_id = Column(BigInteger, ForeignKey('accounting_bank_statement.id', ondelete='CASCADE'), nullable=False, index=True)
    
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    status = Column(String(50), nullable=False, default="RUNNING")  # RUNNING, SUCCESS, FAILED
    
    openai_model = Column(String(50), nullable=True)
    openai_request_id = Column(Text, nullable=True)
    
    transactions_total = Column(Integer, default=0)
    transactions_inserted = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    balance_difference = Column(Numeric(14, 2), nullable=True)
    
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)


class AccountingProcessLog(Base):
    """Detailed logs for admin UI debugging."""
    __tablename__ = "accounting_process_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bank_statement_id = Column(BigInteger, ForeignKey('accounting_bank_statement.id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    level = Column(Text, nullable=False, default='INFO')  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    details = Column(JSONB, nullable=True)


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
    # Physical columns holding encrypted blobs when written via properties.
    _access_token = Column("access_token", Text, nullable=True)
    _refresh_token = Column("refresh_token", Text, nullable=True)
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

    # ------------------------------------------------------------------
    # Encrypted token accessors (per-account tokens in ebay_tokens)
    # ------------------------------------------------------------------
    @property
    def access_token(self) -> str | None:
        from app.utils import crypto

        raw = self._access_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @access_token.setter
    def access_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._access_token = None
        else:
            self._access_token = crypto.encrypt(value)

    @property
    def refresh_token(self) -> str | None:
        from app.utils import crypto

        raw = self._refresh_token
        if raw is None:
            return None
        return crypto.decrypt(raw)

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        from app.utils import crypto

        if value is None or value == "":
            self._refresh_token = None
        else:
            self._refresh_token = crypto.encrypt(value)


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


class EbayOrder(Base):
    __tablename__ = "ebay_orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(String(100), nullable=False)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    ebay_account_id = Column(String(36), nullable=True)
    ebay_user_id = Column(String(100), nullable=True)

    creation_date = Column(DateTime(timezone=True), nullable=True)
    last_modified_date = Column(DateTime(timezone=True), nullable=True)
    
    order_payment_status = Column(String(50), nullable=True)
    order_fulfillment_status = Column(String(50), nullable=True)
    
    buyer_username = Column(String(100), nullable=True)
    buyer_email = Column(String(100), nullable=True)
    buyer_registered = Column(String(100), nullable=True)
    
    total_amount = Column(Numeric(14, 2), nullable=True)
    total_currency = Column(String(10), nullable=True)
    
    order_total_value = Column(Numeric(14, 2), nullable=True)
    order_total_currency = Column(String(10), nullable=True)
    
    line_items_count = Column(Integer, nullable=True)
    
    tracking_number = Column(String(100), nullable=True)
    ship_to_name = Column(String(100), nullable=True)
    ship_to_city = Column(String(100), nullable=True)
    ship_to_state = Column(String(100), nullable=True)
    ship_to_postal_code = Column(String(50), nullable=True)
    ship_to_country_code = Column(String(10), nullable=True)
    
    order_data = Column(JSONB, nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_ebay_orders_user_id', 'user_id'),
        Index('idx_ebay_orders_ebay_account_id', 'ebay_account_id'),
        Index('idx_ebay_orders_creation_date', 'creation_date'),
        Index('idx_ebay_orders_order_id', 'order_id'),
        UniqueConstraint('order_id', 'user_id', name='uq_ebay_orders_order_id_user_id'),
    )


class EbayEvent(Base):
    """Unified inbox of all eBay-related events (webhooks, pollers, manual).

    This table is write-heavy and used as a shared inbox for both Notification
    API webhooks and polling-based workers. Downstream processors mark events
    as processed via ``processed_at`` and may record structured error details
    in ``processing_error``.
    """

    __tablename__ = "ebay_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Provenance
    source = Column(Text, nullable=False)  # notification, rest_poll, trading_poll, manual_test, ...
    channel = Column(Text, nullable=False)  # commerce_notification, sell_fulfillment_api, trading_messages, ...
    topic = Column(Text, nullable=True)

    # Logical entity
    entity_type = Column(Text, nullable=True)
    entity_id = Column(Text, nullable=True)

    # Account context (seller account / username / ebay_user_id or similar)
    ebay_account = Column(Text, nullable=True)

    # Timestamps
    event_time = Column(DateTime(timezone=True), nullable=True)
    publish_time = Column(DateTime(timezone=True), nullable=True)

    # Processing status on our side
    status = Column(Text, nullable=False, default="RECEIVED")
    error = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processing_error = Column(JSONB, nullable=True)

    # Metadata & payload
    headers = Column(JSONB, nullable=False, default=dict)
    signature_valid = Column(Boolean, nullable=True)
    signature_kid = Column(Text, nullable=True)

    payload = Column(JSONB, nullable=False)


class EbayStatusBuyer(Base):
    """Dictionary of internal BUYING statuses (legacy tbl_ebay_buyer Status dictionary).

    Backed by public.ebay_status_buyer. Rows are referenced by ebay_buyer.item_status_id.
    """

    __tablename__ = "ebay_status_buyer"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False, unique=True)
    label = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False)
    color_hex = Column(Text, nullable=True)
    text_color_hex = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EbayBuyer(Base):
    """Legacy tbl_ebay_buyer equivalent backed by Supabase/Postgres.

    Stores per-account purchase line-items where our connected account is the buyer.
    """

    __tablename__ = "ebay_buyer"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Multi-account context
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    # Core eBay identifiers
    item_id = Column(Text, nullable=True, index=True)
    transaction_id = Column(Text, nullable=True, index=True)
    order_line_item_id = Column(Text, nullable=True, index=True)

    title = Column(Text, nullable=True)
    shipping_carrier = Column(Text, nullable=True)
    tracking_number = Column(Text, nullable=True, index=True)
    buyer_checkout_message = Column(Text, nullable=True)
    condition_display_name = Column(Text, nullable=True)

    seller_email = Column(Text, nullable=True)
    seller_id = Column(Text, nullable=True, index=True)
    seller_site = Column(Text, nullable=True)
    seller_location = Column(Text, nullable=True)

    quantity_purchased = Column(Integer, nullable=True)
    current_price = Column(Numeric(18, 2), nullable=True)
    shipping_service_cost = Column(Numeric(18, 2), nullable=True)
    total_price = Column(Numeric(18, 2), nullable=True)
    total_transaction_price = Column(Numeric(18, 2), nullable=True)

    payment_hold_status = Column(Text, nullable=True)
    buyer_paid_status = Column(Text, nullable=True)
    paid_time = Column(DateTime(timezone=True), nullable=True, index=True)
    shipped_time = Column(DateTime(timezone=True), nullable=True)
    platform = Column(Text, nullable=True)

    buyer_id = Column(Text, nullable=True, index=True)  # eBay buyer username
    item_url = Column(Text, nullable=True)
    gallery_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    private_notes = Column(Text, nullable=True)
    my_comment = Column(Text, nullable=True)  # internal note
    storage = Column(Text, nullable=True)  # warehouse location

    model_id = Column(Integer, nullable=True, index=True)

    # Warehouse-driven item status & comment
    item_status_id = Column(Integer, ForeignKey('ebay_status_buyer.id', ondelete='SET NULL'), nullable=True, index=True)
    item_status_updated_at = Column(DateTime(timezone=True), nullable=True)
    item_status_updated_by = Column(Text, nullable=True)

    comment = Column(Text, nullable=True)
    comment_updated_at = Column(DateTime(timezone=True), nullable=True)
    comment_updated_by = Column(Text, nullable=True)

    # Record audit fields
    record_created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    record_created_by = Column(Text, nullable=True)
    record_updated_at = Column(DateTime(timezone=True), nullable=True)
    record_updated_by = Column(Text, nullable=True)

    refund_flag = Column(Boolean, nullable=True)
    refund_amount = Column(Numeric(18, 2), nullable=True)
    profit = Column(Numeric(18, 2), nullable=True)
    profit_updated_at = Column(DateTime(timezone=True), nullable=True)
    profit_updated_by = Column(Text, nullable=True)

    account = relationship("EbayAccount")
    status = relationship("EbayStatusBuyer")

    __table_args__ = (
        # Prevent duplicate purchase rows per account; used for upserts.
        Index(
            'uq_ebay_buyer_account_item_txn',
            'ebay_account_id',
            'item_id',
            'transaction_id',
            'order_line_item_id',
            unique=True,
        ),
        Index('idx_ebay_buyer_tracking', 'tracking_number'),
    )


class EbayBuyerLog(Base):
    """Change log for status/comment edits on ebay_buyer.

    Kept under the legacy table name tbl_ebay_buyer_log for easier mapping.
    """

    __tablename__ = "tbl_ebay_buyer_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ebay_buyer_id = Column(Integer, ForeignKey('ebay_buyer.id', ondelete='CASCADE'), nullable=False, index=True)

    change_type = Column(Text, nullable=False)  # 'status', 'comment', 'status+comment'
    old_status_id = Column(Integer, ForeignKey('ebay_status_buyer.id', ondelete='SET NULL'), nullable=True)
    new_status_id = Column(Integer, ForeignKey('ebay_status_buyer.id', ondelete='SET NULL'), nullable=True)
    old_comment = Column(Text, nullable=True)
    new_comment = Column(Text, nullable=True)

    changed_by_user_id = Column(String(36), nullable=True)
    changed_by_username = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    meta = Column(JSONB, nullable=True)

    __table_args__ = (
        Index('idx_ebay_buyer_log_buyer_changed_at', 'ebay_buyer_id', 'changed_at'),
    )


class EbaySnipeStatus(str, enum.Enum):
    """Lifecycle states for a sniper entry.

    pending   – (legacy) created but not fully scheduled; in v2 we generally
                move new snipes directly into "scheduled" once fire_at is
                computed.
    scheduled – fully validated, has a concrete fire_at and is waiting for the
                worker to execute.
    bidding   – worker is actively attempting to place a bid for this snipe.
    executed_stub – internal/testing state used by the stub worker
                     implementation; real bidding will eventually use
                     "bidding" + terminal states instead.
    won       – auction finished and the snipe won.
    lost      – auction finished and the snipe lost.
    error     – a worker or eBay API error occurred; see result_message.
    cancelled – user cancelled the snipe before execution.
    """

    pending = "pending"
    scheduled = "scheduled"
    bidding = "bidding"
    executed_stub = "executed_stub"
    won = "won"
    lost = "lost"
    error = "error"
    cancelled = "cancelled"


class EbaySnipe(Base):
    """Internal Bidnapper-like sniper entry.

    Stores a scheduled last-second bid for an eBay auction along with cached
    item metadata and execution result fields.

    In Sniper v2, each row also has a concrete fire_at timestamp that represents
    the exact moment when the worker should attempt to place the bid. Storing
    fire_at explicitly makes worker queries simpler and avoids recomputing the
    schedule expression on every tick.
    """

    __tablename__ = "ebay_snipes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=True, index=True)

    item_id = Column(String(100), nullable=False, index=True)
    title = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)

    end_time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Exact scheduled execution time (end_time - seconds_before_end). This is
    # computed in application code whenever a snipe is created or its timing
    # parameters change so that workers can simply query on fire_at.
    fire_at = Column(DateTime(timezone=True), nullable=False, index=True)

    max_bid_amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(CHAR(3), nullable=False, default="USD")
    seconds_before_end = Column(Integer, nullable=False, default=5)

    status = Column(String(32), nullable=False, default=EbaySnipeStatus.pending.value, index=True)

    current_bid_at_creation = Column(Numeric(14, 2), nullable=True)
    result_price = Column(Numeric(14, 2), nullable=True)
    result_message = Column(Text, nullable=True)

    # Optional free-form user note describing the intent/context of the snipe.
    comment = Column(Text, nullable=True)

    # True once at least one bid attempt was made for this snipe. This is a
    # denormalised helper flag; detailed history lives in EbaySnipeLog.
    has_bid = Column(Boolean, nullable=False, default=False)

    contingency_group_id = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="ebay_snipes")
    ebay_account = relationship("EbayAccount", backref="snipes")
    logs = relationship("EbaySnipeLog", back_populates="snipe", cascade="all, delete-orphan")


class EbaySnipeLog(Base):
    """Per-snipe audit log for sniper executions and eBay responses."""

    __tablename__ = "ebay_snipe_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snipe_id = Column(String(36), ForeignKey("ebay_snipes.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    event_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=True)
    ebay_bid_id = Column(String(100), nullable=True)
    correlation_id = Column(String(100), nullable=True)
    http_status = Column(Integer, nullable=True)

    # Raw payload or structured summary of the eBay interaction. Stored as
    # text for now; callers may persist JSON-serialised content when needed.
    payload = Column(Text, nullable=True)

    # Short human-readable summary suitable for direct display in the UI.
    message = Column(Text, nullable=True)

    snipe = relationship("EbaySnipe", back_populates="logs")


class Message(Base):
    __tablename__ = "ebay_messages"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
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

    # Flags and direction
    is_read = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    direction = Column(String(20), nullable=True)

    # Timestamps
    message_date = Column(DateTime(timezone=True), nullable=True)
    # Optional canonical timestamptz used by new code paths when present.
    message_at = Column(DateTime(timezone=True), nullable=True)
    read_date = Column(DateTime(timezone=True), nullable=True)

    # Order / item linkage
    order_id = Column(String(100), nullable=True)
    listing_id = Column(String(100), nullable=True)

    # Case / dispute linkage
    case_id = Column(Text, nullable=True)
    case_type = Column(Text, nullable=True)
    inquiry_id = Column(Text, nullable=True)
    return_id = Column(Text, nullable=True)
    payment_dispute_id = Column(Text, nullable=True)
    transaction_id = Column(Text, nullable=True)

    # Classification and topic
    is_case_related = Column(Boolean, nullable=False, default=False)
    message_topic = Column(Text, nullable=True)
    case_event_type = Column(Text, nullable=True)

    # Raw + parsed representations
    raw_data = Column(Text, nullable=True)
    parsed_body = Column(JSONB, nullable=True)

    # Attachments and preview
    has_attachments = Column(Boolean, nullable=False, default=False)
    attachments_meta = Column(JSONB, nullable=False, default=list)
    preview_text = Column(Text, nullable=True)

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


class EbaySearchWatch(Base):
    """User-defined eBay auto-search rule.

    Stores per-user watch rules for periodically querying the eBay Browse API
    and generating internal notifications when new matching listings appear.
    """

    __tablename__ = "ebay_search_watches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Human-readable name and core query parameters
    name = Column(Text, nullable=False)
    keywords = Column(Text, nullable=False)

    # Optional upper bound for price + shipping in the listing currency.
    max_total_price = Column(Numeric(14, 2), nullable=True)

    # Simple hint for post-filtering by type of item (e.g. "laptop", "all").
    category_hint = Column(String(50), nullable=True)

    # List of case-insensitive keywords that must NOT appear in title/description
    # (e.g. ["screen", "keyboard", "battery"] to exclude parts).
    exclude_keywords = Column(JSONB, nullable=True)

    marketplace_id = Column(String(20), nullable=False, default="EBAY_US")

    enabled = Column(Boolean, nullable=False, default=True, index=True)

    # Minimal interval between checks for this watch in seconds.
    check_interval_sec = Column(Integer, nullable=False, default=60)

    last_checked_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Small rolling window of recently seen itemIds to avoid duplicate
    # notifications. Stored as JSON list of strings.
    last_seen_item_ids = Column(JSONB, nullable=True)

    # How to notify the user when new matches are found. Initial values:
    # - "task" – create/append to an internal Task + TaskNotification
    # - "none" – do not generate notifications (rule only for manual checks)
    notification_mode = Column(String(20), nullable=False, default="task")

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="ebay_search_watches")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String(20), nullable=False)  # 'task' or 'reminder'

    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    creator_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    status = Column(String(32), nullable=False)
    priority = Column(String(20), nullable=False, default="normal")  # low, normal, high

    due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    snooze_until = Column(DateTime(timezone=True), nullable=True)

    is_popup = Column(Boolean, nullable=False, server_default="true")

    # Archiving / importance flags
    is_archived = Column(Boolean, nullable=False, default=False, server_default="false")
    is_important = Column(Boolean, nullable=False, default=False, server_default="false")

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[creator_id])
    assignee = relationship("User", foreign_keys=[assignee_id])

    comments = relationship(
        "TaskComment",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskComment.created_at",
    )
    notifications = relationship(
        "TaskNotification",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_tasks_assignee_status", "assignee_id", "status"),
        Index("idx_tasks_creator_status", "creator_id", "status"),
        Index("idx_tasks_type_status", "type", "status"),
        Index("idx_tasks_due_at", "due_at"),
    )


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    body = Column(Text, nullable=False)
    kind = Column(String(50), nullable=False, default="comment")  # comment, status_change, snooze, system
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    task = relationship("Task", back_populates="comments")


class TaskNotification(Base):
    __tablename__ = "task_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    kind = Column(String(50), nullable=False)  # task_assigned, task_status_changed, task_comment_added, reminder_fired
    status = Column(String(20), nullable=False, default="unread")  # unread, read, dismissed

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="notifications")

    __table_args__ = (
        Index("idx_task_notifications_user_status_created", "user_id", "status", "created_at"),
    )


class ShippingJobStatus(str, enum.Enum):
    NEW = "NEW"
    PICKING = "PICKING"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class ShippingLabelProvider(str, enum.Enum):
    EBAY_LOGISTICS = "EBAY_LOGISTICS"
    EXTERNAL = "EXTERNAL"
    MANUAL = "MANUAL"


class ShippingStatusSource(str, enum.Enum):
    WAREHOUSE_SCAN = "WAREHOUSE_SCAN"
    API = "API"
    MANUAL = "MANUAL"


class ShippingJob(Base):
    __tablename__ = "shipping_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    ebay_account_id = Column(String(36), ForeignKey("ebay_accounts.id"), nullable=True, index=True)
    ebay_order_id = Column(Text, nullable=True, index=True)
    ebay_order_line_item_ids = Column(JSONB, nullable=True)  # list[str]

    buyer_user_id = Column(Text, nullable=True)
    buyer_name = Column(Text, nullable=True)
    ship_to_address = Column(JSONB, nullable=True)

    warehouse_id = Column(Text, nullable=True)
    storage_ids = Column(JSONB, nullable=True)  # list[str]

    status = Column(Enum(ShippingJobStatus), nullable=False, default=ShippingJobStatus.NEW, index=True)

    # Optional pointer to the primary label for this job. Kept as a plain
    # string to avoid circular FK constraints with shipping_labels.
    label_id = Column(String(36), nullable=True)

    paid_time = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    packages = relationship("ShippingPackage", back_populates="job", cascade="all, delete-orphan")
    label = relationship("ShippingLabel", back_populates="job", uselist=False)
    status_logs = relationship("ShippingStatusLog", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_shipping_jobs_status_warehouse", "status", "warehouse_id"),
        Index("idx_shipping_jobs_ebay_order_id", "ebay_order_id"),
    )


class ShippingPackage(Base):
    __tablename__ = "shipping_packages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipping_job_id = Column(String(36), ForeignKey("shipping_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    combined_for_buyer = Column(Boolean, nullable=False, default=False)

    weight_oz = Column(Numeric(10, 2), nullable=True)
    length_in = Column(Numeric(10, 2), nullable=True)
    width_in = Column(Numeric(10, 2), nullable=True)
    height_in = Column(Numeric(10, 2), nullable=True)

    package_type = Column(Text, nullable=True)  # BOX, ENVELOPE, POLYMAILER, etc.
    carrier_preference = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("ShippingJob", back_populates="packages")


class ShippingLabel(Base):
    __tablename__ = "shipping_labels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipping_job_id = Column(String(36), ForeignKey("shipping_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    provider = Column(Enum(ShippingLabelProvider), nullable=False)
    provider_shipment_id = Column(Text, nullable=True)

    tracking_number = Column(Text, nullable=True, index=True)
    carrier = Column(Text, nullable=True)
    service_name = Column(Text, nullable=True)

    label_url = Column(Text, nullable=True)
    label_file_type = Column(Text, nullable=True)  # pdf, zpl, etc.

    label_cost_amount = Column(Numeric(12, 2), nullable=True)
    label_cost_currency = Column(CHAR(3), nullable=False, default="USD")

    purchased_at = Column(DateTime(timezone=True), nullable=True, index=True)
    voided = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("ShippingJob", back_populates="label")

    __table_args__ = (
        Index("idx_shipping_labels_provider_shipment", "provider", "provider_shipment_id"),
    )


class ShippingStatusLog(Base):
    __tablename__ = "shipping_status_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipping_job_id = Column(String(36), ForeignKey("shipping_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    status_before = Column(Enum(ShippingJobStatus), nullable=True)
    status_after = Column(Enum(ShippingJobStatus), nullable=False)

    source = Column(Enum(ShippingStatusSource), nullable=False, default=ShippingStatusSource.MANUAL)
    reason = Column(Text, nullable=True)

    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    job = relationship("ShippingJob", back_populates="status_logs")
