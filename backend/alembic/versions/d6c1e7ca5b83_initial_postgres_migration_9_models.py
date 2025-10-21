"""Initial Postgres migration - 9 models

Revision ID: d6c1e7ca5b83
Revises: 
Create Date: 2025-10-21 10:53:32.349105

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6c1e7ca5b83'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create all 9 tables (idempotent)."""
    from sqlalchemy import inspect
    from alembic import op as alembic_op
    
    conn = alembic_op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'users' in existing_tables:
        return
    
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('ebay_connected', sa.Boolean(), default=False),
        sa.Column('ebay_access_token', sa.Text(), nullable=True),
        sa.Column('ebay_refresh_token', sa.Text(), nullable=True),
        sa.Column('ebay_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('ebay_environment', sa.String(20), default='sandbox'),
    )
    op.create_index('idx_user_email', 'users', ['email'])
    op.create_index('idx_user_role', 'users', ['role'])
    
    op.create_table(
        'warehouses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('capacity', sa.Integer(), default=0),
        sa.Column('warehouse_type', sa.String(50), nullable=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rec_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    
    op.create_table(
        'buying',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('item_id', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('buyer_id', sa.String(100), nullable=True, index=True),
        sa.Column('buyer_username', sa.String(100), nullable=True),
        sa.Column('seller_id', sa.String(100), nullable=True, index=True),
        sa.Column('seller_username', sa.String(100), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('paid_date', sa.DateTime(), nullable=True, index=True),
        sa.Column('amount_paid', sa.Float(), default=0.0),
        sa.Column('sale_price', sa.Float(), default=0.0),
        sa.Column('ebay_fee', sa.Float(), default=0.0),
        sa.Column('shipping_cost', sa.Float(), default=0.0),
        sa.Column('refund', sa.Float(), default=0.0),
        sa.Column('profit', sa.Float(), default=0.0),
        sa.Column('status', sa.String(50), default='unpaid', index=True),
        sa.Column('storage', sa.String(100), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('author', sa.String(100), nullable=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rec_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_buying_item_id', 'buying', ['item_id'])
    op.create_index('idx_buying_buyer_id', 'buying', ['buyer_id'])
    op.create_index('idx_buying_seller_id', 'buying', ['seller_id'])
    op.create_index('idx_buying_status', 'buying', ['status'])
    op.create_index('idx_buying_paid_date', 'buying', ['paid_date'])
    
    op.create_table(
        'sku',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('sku_code', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('category', sa.String(100), nullable=True, index=True),
        sa.Column('condition', sa.String(50), nullable=True),
        sa.Column('part_number', sa.String(100), nullable=True),
        sa.Column('price', sa.Float(), default=0.0),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('brand', sa.String(100), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rec_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_sku_code', 'sku', ['sku_code'])
    op.create_index('idx_sku_category', 'sku', ['category'])
    
    op.create_table(
        'listings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('sku_id', sa.Integer(), nullable=False),
        sa.Column('ebay_listing_id', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('ebay_item_id', sa.String(100), nullable=True, index=True),
        sa.Column('price', sa.Float(), default=0.0),
        sa.Column('ebay_price', sa.Float(), default=0.0),
        sa.Column('shipping_group', sa.String(100), nullable=True),
        sa.Column('condition', sa.String(50), nullable=True),
        sa.Column('storage', sa.String(100), nullable=True),
        sa.Column('warehouse_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('listed_date', sa.DateTime(), nullable=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rec_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['sku_id'], ['sku.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
    )
    op.create_index('idx_listing_ebay_id', 'listings', ['ebay_listing_id'])
    op.create_index('idx_listing_item_id', 'listings', ['ebay_item_id'])
    op.create_index('idx_listing_sku_id', 'listings', ['sku_id'])
    
    op.create_table(
        'inventory',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('sku_id', sa.Integer(), nullable=False),
        sa.Column('storage', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), default='available', index=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('price', sa.Float(), default=0.0),
        sa.Column('warehouse_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), default=1),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rec_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['sku_id'], ['sku.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
    )
    op.create_index('idx_inventory_sku_id', 'inventory', ['sku_id'])
    op.create_index('idx_inventory_status', 'inventory', ['status'])
    op.create_index('idx_inventory_warehouse_id', 'inventory', ['warehouse_id'])
    
    op.create_table(
        'returns',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('return_id', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('item_id', sa.String(100), nullable=True),
        sa.Column('ebay_order_id', sa.String(100), nullable=True, index=True),
        sa.Column('buyer', sa.String(100), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('sale_price', sa.Float(), default=0.0),
        sa.Column('refund_amount', sa.Float(), default=0.0),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('return_date', sa.DateTime(), nullable=True),
        sa.Column('resolved_date', sa.DateTime(), nullable=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rec_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_return_return_id', 'returns', ['return_id'])
    op.create_index('idx_return_order_id', 'returns', ['ebay_order_id'])
    
    op.create_table(
        'sync_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('endpoint', sa.String(255), nullable=False),
        sa.Column('record_count', sa.Integer(), default=0),
        sa.Column('duration', sa.Float(), default=0.0),
        sa.Column('status', sa.String(50), nullable=False, index=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sync_started_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('sync_completed_at', sa.DateTime(), nullable=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_synclog_user_id', 'sync_logs', ['user_id'])
    op.create_index('idx_synclog_status', 'sync_logs', ['status'])
    op.create_index('idx_synclog_started', 'sync_logs', ['sync_started_at'])
    
    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('report_type', sa.String(100), nullable=False, index=True),
        sa.Column('filters', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(255), nullable=True),
        sa.Column('generated_by', sa.String(36), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('rec_created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['generated_by'], ['users.id']),
    )
    op.create_index('idx_report_type', 'reports', ['report_type'])
    op.create_index('idx_report_generated_at', 'reports', ['generated_at'])
    
    op.create_table(
        'password_reset_tokens',
        sa.Column('token', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('used', sa.Boolean(), default=False),
    )
    op.create_index('idx_reset_token_email', 'password_reset_tokens', ['email'])
    op.create_index('idx_reset_token_expires', 'password_reset_tokens', ['expires_at'])


def downgrade() -> None:
    """Downgrade schema - drop all tables."""
    op.drop_table('password_reset_tokens')
    op.drop_table('reports')
    op.drop_table('sync_logs')
    op.drop_table('returns')
    op.drop_table('inventory')
    op.drop_table('listings')
    op.drop_table('sku')
    op.drop_table('buying')
    op.drop_table('warehouses')
    op.drop_table('users')
