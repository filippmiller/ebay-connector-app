from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey, Text, UniqueConstraint, JSON
from sqlalchemy.sql import func
from app.models_sqlalchemy import Base
import uuid

class EbayInventoryOffer(Base):
    __tablename__ = "ebay_inventory_offers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id'), nullable=False, index=True)
    offer_id = Column(String(100), nullable=False)
    sku = Column(String(100), index=True)
    marketplace_id = Column(String(50))
    listing_id = Column(String(100), index=True, nullable=True)
    
    status = Column(String(50)) # PUBLISHED, UNPUBLISHED
    listing_status = Column(String(50), nullable=True) # ACTIVE, ENDED
    
    price_currency = Column(String(10))
    price_value = Column(Numeric(10, 2))
    
    available_quantity = Column(Integer)
    sold_quantity = Column(Integer, nullable=True)
    quantity_limit_per_buyer = Column(Integer, nullable=True)
    
    vat_percentage = Column(Numeric(5, 2), nullable=True)
    merchant_location_key = Column(String(100), nullable=True)
    
    raw_payload = Column(JSON)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('ebay_account_id', 'offer_id', name='uq_ebay_inventory_offer_account_offer'),
    )

class EbayInventoryOfferEvent(Base):
    __tablename__ = "ebay_inventory_offer_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id'), nullable=False, index=True)
    offer_id = Column(String(100), nullable=False, index=True)
    sku = Column(String(100))
    
    event_type = Column(String(50)) # created, price_change, qty_change, status_change, policy_change, snapshot
    snapshot_signature = Column(String(64), nullable=False)
    
    changed_fields = Column(JSON)
    snapshot_payload = Column(JSON)
    
    # Denormalized fields for quick access
    price_currency = Column(String(10))
    price_value = Column(Numeric(10, 2))
    available_quantity = Column(Integer)
    sold_quantity = Column(Integer, nullable=True)
    status = Column(String(50))
    listing_status = Column(String(50), nullable=True)
    
    source = Column(String(50)) # inventory.getOffers, internal.updateOffer
    fetched_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('ebay_account_id', 'offer_id', 'snapshot_signature', name='uq_ebay_inventory_offer_event_dedupe'),
    )
