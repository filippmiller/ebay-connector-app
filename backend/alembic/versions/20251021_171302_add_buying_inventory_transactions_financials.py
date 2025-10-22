"""Add buying inventory transactions financials tables

Revision ID: add_core_ops_tables
Revises: 20251021_155209_add_normalized_columns
Create Date: 2025-10-21 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Numeric, CHAR

revision = 'add_core_ops_tables'
down_revision = '20251021_155209_add_normalized_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add purchases, transactions, fees, payouts, and update inventory"""
    
    # Create purchases table
    op.create_table(
        'purchases',
        sa.Column('purchase_id', sa.String(100), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('creation_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_modified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('buyer_username', sa.String(100), nullable=True),
        sa.Column('seller_username', sa.String(100), nullable=True),
        sa.Column('total_value', Numeric(14, 2), nullable=True),
        sa.Column('total_currency', CHAR(3), nullable=True),
        sa.Column('payment_status', sa.String(50), nullable=True),
        sa.Column('fulfillment_status', sa.String(50), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('ship_to_name', sa.String(255), nullable=True),
        sa.Column('ship_to_city', sa.String(100), nullable=True),
        sa.Column('ship_to_state', sa.String(100), nullable=True),
        sa.Column('ship_to_postal', sa.String(20), nullable=True),
        sa.Column('ship_to_country', CHAR(2), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create indexes for purchases
    op.create_index('idx_purchase_creation_date', 'purchases', ['creation_date'])
    op.create_index('idx_purchase_buyer', 'purchases', ['buyer_username'])
    op.create_index('idx_purchase_seller', 'purchases', ['seller_username'])
    op.create_index('idx_purchase_payment_status', 'purchases', ['payment_status'])
    op.create_index('idx_purchase_fulfillment_status', 'purchases', ['fulfillment_status'])
    op.create_index('idx_purchase_user_id', 'purchases', ['user_id'])
    
    # Create purchase_line_items table
    op.create_table(
        'purchase_line_items',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('purchase_id', sa.String(100), sa.ForeignKey('purchases.purchase_id'), nullable=False),
        sa.Column('line_item_id', sa.String(100), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Integer(), default=0),
        sa.Column('total_value', Numeric(14, 2), nullable=True),
        sa.Column('currency', CHAR(3), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create indexes for purchase_line_items
    op.create_index('idx_purch_line_purchase_id', 'purchase_line_items', ['purchase_id'])
    op.create_index('idx_purch_line_sku', 'purchase_line_items', ['sku'])
    op.create_index('idx_purch_line_unique', 'purchase_line_items', ['purchase_id', 'line_item_id'], unique=True)
    
    # Create transactions table
    op.create_table(
        'transactions',
        sa.Column('transaction_id', sa.String(100), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('order_id', sa.String(100), nullable=True),
        sa.Column('line_item_id', sa.String(100), nullable=True),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('buyer_username', sa.String(100), nullable=True),
        sa.Column('sale_value', Numeric(14, 2), nullable=True),
        sa.Column('currency', CHAR(3), nullable=True),
        sa.Column('sale_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('quantity', sa.Integer(), default=0),
        sa.Column('shipping_charged', Numeric(14, 2), nullable=True),
        sa.Column('tax_collected', Numeric(14, 2), nullable=True),
        sa.Column('fulfillment_status', sa.String(50), nullable=True),
        sa.Column('payment_status', sa.String(50), nullable=True),
        sa.Column('profit', Numeric(14, 2), nullable=True),
        sa.Column('profit_status', sa.String(50), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create indexes for transactions
    op.create_index('idx_txn_order_id', 'transactions', ['order_id'])
    op.create_index('idx_txn_sale_date', 'transactions', ['sale_date'])
    op.create_index('idx_txn_buyer', 'transactions', ['buyer_username'])
    op.create_index('idx_txn_sku', 'transactions', ['sku'])
    op.create_index('idx_txn_user_id', 'transactions', ['user_id'])
    
    # Create fees table
    op.create_table(
        'fees',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=True),
        sa.Column('source_id', sa.String(100), nullable=True),
        sa.Column('fee_type', sa.String(100), nullable=True),
        sa.Column('amount', Numeric(14, 2), nullable=True),
        sa.Column('currency', CHAR(3), nullable=True),
        sa.Column('assessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create indexes for fees
    op.create_index('idx_fee_source_id', 'fees', ['source_id'])
    op.create_index('idx_fee_type', 'fees', ['fee_type'])
    op.create_index('idx_fee_assessed_at', 'fees', ['assessed_at'])
    op.create_index('idx_fee_user_id', 'fees', ['user_id'])
    
    # Create payouts table
    op.create_table(
        'payouts',
        sa.Column('payout_id', sa.String(100), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('total_amount', Numeric(14, 2), nullable=True),
        sa.Column('currency', CHAR(3), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('payout_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create indexes for payouts
    op.create_index('idx_payout_date', 'payouts', ['payout_date'])
    op.create_index('idx_payout_user_id', 'payouts', ['user_id'])
    
    # Create payout_items table
    op.create_table(
        'payout_items',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('payout_id', sa.String(100), sa.ForeignKey('payouts.payout_id'), nullable=False),
        sa.Column('type', sa.String(50), nullable=True),
        sa.Column('reference_id', sa.String(100), nullable=True),
        sa.Column('amount', Numeric(14, 2), nullable=True),
        sa.Column('currency', CHAR(3), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create indexes for payout_items
    op.create_index('idx_payout_item_payout_id', 'payout_items', ['payout_id'])
    op.create_index('idx_payout_item_reference_id', 'payout_items', ['reference_id'])
    
    # Update inventory table with new columns
    op.add_column('inventory', sa.Column('sku_code', sa.String(100), nullable=True))
    op.add_column('inventory', sa.Column('title', sa.Text(), nullable=True))
    op.add_column('inventory', sa.Column('condition', sa.String(50), nullable=True))
    op.add_column('inventory', sa.Column('cost', Numeric(14, 2), nullable=True))
    op.add_column('inventory', sa.Column('expected_price', Numeric(14, 2), nullable=True))
    op.add_column('inventory', sa.Column('image_url', sa.Text(), nullable=True))
    op.add_column('inventory', sa.Column('notes', sa.Text(), nullable=True))
    
    # Add indexes for new inventory columns
    op.create_index('idx_inventory_sku_code', 'inventory', ['sku_code'])
    op.create_index('idx_inventory_storage', 'inventory', ['storage'])


def downgrade() -> None:
    """Remove all new tables and columns"""
    op.drop_table('payout_items')
    op.drop_table('payouts')
    op.drop_table('fees')
    op.drop_table('transactions')
    op.drop_table('purchase_line_items')
    op.drop_table('purchases')
    
    op.drop_index('idx_inventory_storage', 'inventory')
    op.drop_index('idx_inventory_sku_code', 'inventory')
    op.drop_column('inventory', 'notes')
    op.drop_column('inventory', 'image_url')
    op.drop_column('inventory', 'expected_price')
    op.drop_column('inventory', 'cost')
    op.drop_column('inventory', 'condition')
    op.drop_column('inventory', 'title')
    op.drop_column('inventory', 'sku_code')
