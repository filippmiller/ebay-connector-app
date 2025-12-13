"""Add inventory offers and events tables

Revision ID: add_inventory_offers_20251203
Revises: ebay_returns_20251201
Create Date: 2025-12-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_inventory_offers_20251203'
down_revision = 'ebay_returns_20251201'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create ebay_inventory_offers table
    op.create_table('ebay_inventory_offers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('ebay_account_id', sa.String(length=36), nullable=False),
        sa.Column('offer_id', sa.String(length=100), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('marketplace_id', sa.String(length=50), nullable=True),
        sa.Column('listing_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('listing_status', sa.String(length=50), nullable=True),
        sa.Column('price_currency', sa.String(length=10), nullable=True),
        sa.Column('price_value', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('available_quantity', sa.Integer(), nullable=True),
        sa.Column('sold_quantity', sa.Integer(), nullable=True),
        sa.Column('quantity_limit_per_buyer', sa.Integer(), nullable=True),
        sa.Column('vat_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('merchant_location_key', sa.String(length=100), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ebay_account_id', 'offer_id', name='uq_ebay_inventory_offer_account_offer')
    )
    op.create_index(op.f('idx_ebay_inventory_offers_ebay_account_id'), 'ebay_inventory_offers', ['ebay_account_id'], unique=False)
    op.create_index(op.f('idx_ebay_inventory_offers_listing_id'), 'ebay_inventory_offers', ['listing_id'], unique=False)
    op.create_index(op.f('idx_ebay_inventory_offers_sku'), 'ebay_inventory_offers', ['sku'], unique=False)

    # Create ebay_inventory_offer_events table
    op.create_table('ebay_inventory_offer_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('ebay_account_id', sa.String(length=36), nullable=False),
        sa.Column('offer_id', sa.String(length=100), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=True),
        sa.Column('snapshot_signature', sa.String(length=64), nullable=False),
        sa.Column('changed_fields', sa.JSON(), nullable=True),
        sa.Column('snapshot_payload', sa.JSON(), nullable=True),
        sa.Column('price_currency', sa.String(length=10), nullable=True),
        sa.Column('price_value', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('available_quantity', sa.Integer(), nullable=True),
        sa.Column('sold_quantity', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('listing_status', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ebay_account_id', 'offer_id', 'snapshot_signature', name='uq_ebay_inventory_offer_event_dedupe')
    )
    op.create_index(op.f('idx_ebay_inventory_offer_events_ebay_account_id'), 'ebay_inventory_offer_events', ['ebay_account_id'], unique=False)
    op.create_index(op.f('idx_ebay_inventory_offer_events_offer_id'), 'ebay_inventory_offer_events', ['offer_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('idx_ebay_inventory_offer_events_offer_id'), table_name='ebay_inventory_offer_events')
    op.drop_index(op.f('idx_ebay_inventory_offer_events_ebay_account_id'), table_name='ebay_inventory_offer_events')
    op.drop_table('ebay_inventory_offer_events')
    op.drop_index(op.f('idx_ebay_inventory_offers_sku'), table_name='ebay_inventory_offers')
    op.drop_index(op.f('idx_ebay_inventory_offers_listing_id'), table_name='ebay_inventory_offers')
    op.drop_index(op.f('idx_ebay_inventory_offers_ebay_account_id'), table_name='ebay_inventory_offers')
    op.drop_table('ebay_inventory_offers')
