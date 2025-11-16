"""Add ebay_active_inventory snapshot table

Revision ID: add_active_inventory_snapshot_001
Revises: 20251115_add_ebay_identity_to_data_tables
Create Date: 2025-11-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Numeric, CHAR, Index


# revision identifiers, used by Alembic.
revision = 'add_active_inventory_snapshot_001'
down_revision = '20251115_add_ebay_identity_to_data_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ebay_active_inventory table if it does not exist."""
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'ebay_active_inventory' not in existing_tables:
        op.create_table(
            'ebay_active_inventory',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('ebay_account_id', sa.String(36), sa.ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('ebay_user_id', sa.Text(), nullable=True),
            sa.Column('sku', sa.String(100), nullable=True),
            sa.Column('item_id', sa.String(100), nullable=True),
            sa.Column('title', sa.Text(), nullable=True),
            sa.Column('quantity_available', sa.Integer(), nullable=True),
            sa.Column('price', Numeric(14, 2), nullable=True),
            sa.Column('currency', CHAR(3), nullable=True),
            sa.Column('listing_status', sa.String(50), nullable=True),
            sa.Column('condition_id', sa.String(50), nullable=True),
            sa.Column('condition_text', sa.Text(), nullable=True),
            sa.Column('raw_payload', JSONB, nullable=True),
            sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        )

        op.create_index('idx_active_inv_account_sku_item', 'ebay_active_inventory', ['ebay_account_id', 'sku', 'item_id'], unique=True)
        op.create_index('idx_active_inv_ebay_user_id', 'ebay_active_inventory', ['ebay_user_id'])
        op.create_index('idx_active_inv_listing_status', 'ebay_active_inventory', ['listing_status'])
        op.create_index('idx_active_inv_last_seen_at', 'ebay_active_inventory', ['last_seen_at'])
    else:
        # Table already exists; ensure required indexes are present
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('ebay_active_inventory')]
        if 'idx_active_inv_account_sku_item' not in existing_indexes:
            op.create_index('idx_active_inv_account_sku_item', 'ebay_active_inventory', ['ebay_account_id', 'sku', 'item_id'], unique=True)
        if 'idx_active_inv_ebay_user_id' not in existing_indexes:
            op.create_index('idx_active_inv_ebay_user_id', 'ebay_active_inventory', ['ebay_user_id'])
        if 'idx_active_inv_listing_status' not in existing_indexes:
            op.create_index('idx_active_inv_listing_status', 'ebay_active_inventory', ['listing_status'])
        if 'idx_active_inv_last_seen_at' not in existing_indexes:
            op.create_index('idx_active_inv_last_seen_at', 'ebay_active_inventory', ['last_seen_at'])


def downgrade() -> None:
    op.drop_index('idx_active_inv_last_seen_at', table_name='ebay_active_inventory')
    op.drop_index('idx_active_inv_listing_status', table_name='ebay_active_inventory')
    op.drop_index('idx_active_inv_ebay_user_id', table_name='ebay_active_inventory')
    op.drop_index('idx_active_inv_account_sku_item', table_name='ebay_active_inventory')
    op.drop_table('ebay_active_inventory')
