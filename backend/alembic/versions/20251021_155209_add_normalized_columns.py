"""Add normalized columns to ebay_orders

Revision ID: add_normalized_cols
Revises: ebay_tables_001
Create Date: 2025-10-21 15:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'add_normalized_cols'
down_revision: Union[str, Sequence[str], None] = 'ebay_tables_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add normalized columns to ebay_orders table (idempotent)"""
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if 'ebay_orders' not in inspector.get_table_names():
        print("⚠️  ebay_orders table does not exist, skipping column additions")
        return
    
    existing_columns = {col['name'] for col in inspector.get_columns('ebay_orders')}
    print(f"✅ Found ebay_orders table with columns: {sorted(existing_columns)}")
    
    # Add buyer_registered column
    if 'buyer_registered' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('buyer_registered', sa.String(100), nullable=True))
    
    # Add order_total columns
    if 'order_total_value' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('order_total_value', sa.Numeric(14, 2), nullable=True))
    if 'order_total_currency' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('order_total_currency', sa.String(3), nullable=True))
    
    # Add line items count
    if 'line_items_count' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('line_items_count', sa.Integer(), nullable=True, server_default='0'))
    
    # Add tracking info
    if 'tracking_number' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('tracking_number', sa.String(100), nullable=True))
    
    # Add shipping address columns
    if 'ship_to_name' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('ship_to_name', sa.String(255), nullable=True))
    if 'ship_to_city' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('ship_to_city', sa.String(100), nullable=True))
    if 'ship_to_state' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('ship_to_state', sa.String(100), nullable=True))
    if 'ship_to_postal_code' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('ship_to_postal_code', sa.String(20), nullable=True))
    if 'ship_to_country_code' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('ship_to_country_code', sa.String(2), nullable=True))
    
    # Add raw_payload column for complete eBay API response
    if 'raw_payload' not in existing_columns:
        op.add_column('ebay_orders', sa.Column('raw_payload', sa.Text(), nullable=True))
    
    # Create order_line_items table if it doesn't exist
    if 'order_line_items' not in inspector.get_table_names():
        op.create_table(
            'order_line_items',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('order_id', sa.String(100), nullable=False),
            sa.Column('line_item_id', sa.String(100), nullable=False),
            sa.Column('sku', sa.String(100), nullable=True),
            sa.Column('title', sa.Text(), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('total_value', sa.Numeric(14, 2), nullable=True),
            sa.Column('currency', sa.String(3), nullable=True),
            sa.Column('raw_payload', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('order_id', 'line_item_id', name='uq_order_line_item')
        )
        op.create_index('idx_line_items_order_id', 'order_line_items', ['order_id'])


def downgrade() -> None:
    """Remove normalized columns"""
    op.drop_table('order_line_items')
    op.drop_column('ebay_orders', 'raw_payload')
    op.drop_column('ebay_orders', 'ship_to_country_code')
    op.drop_column('ebay_orders', 'ship_to_postal_code')
    op.drop_column('ebay_orders', 'ship_to_state')
    op.drop_column('ebay_orders', 'ship_to_city')
    op.drop_column('ebay_orders', 'ship_to_name')
    op.drop_column('ebay_orders', 'tracking_number')
    op.drop_column('ebay_orders', 'line_items_count')
    op.drop_column('ebay_orders', 'order_total_currency')
    op.drop_column('ebay_orders', 'order_total_value')
    op.drop_column('ebay_orders', 'buyer_registered')
