"""Add eBay data tables

Revision ID: ebay_tables_001
Revises: d6c1e7ca5b83
Create Date: 2025-10-21 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'ebay_tables_001'
down_revision: Union[str, Sequence[str], None] = 'd6c1e7ca5b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add eBay data tables (idempotent)"""
    from sqlalchemy import inspect
    from alembic import op as alembic_op
    
    conn = alembic_op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'ebay_orders' in existing_tables:
        return
    
    op.create_table(
        'ebay_orders',
        sa.Column('order_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('creation_date', sa.String(100), nullable=True),
        sa.Column('last_modified_date', sa.String(100), nullable=True),
        sa.Column('order_payment_status', sa.String(50), nullable=True),
        sa.Column('order_fulfillment_status', sa.String(50), nullable=True),
        sa.Column('buyer_username', sa.String(100), nullable=True),
        sa.Column('buyer_email', sa.String(255), nullable=True),
        sa.Column('total_amount', sa.Float(), nullable=True),
        sa.Column('total_currency', sa.String(10), nullable=True),
        sa.Column('order_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('order_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_orders_user_id', 'ebay_orders', ['user_id'])
    op.create_index('idx_ebay_orders_creation_date', 'ebay_orders', ['creation_date'])
    
    op.create_table(
        'ebay_transactions',
        sa.Column('transaction_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('order_id', sa.String(100), nullable=True),
        sa.Column('transaction_date', sa.String(100), nullable=True),
        sa.Column('transaction_type', sa.String(50), nullable=True),
        sa.Column('transaction_status', sa.String(50), nullable=True),
        sa.Column('amount', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('transaction_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('transaction_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_transactions_user_id', 'ebay_transactions', ['user_id'])
    op.create_index('idx_ebay_transactions_order_id', 'ebay_transactions', ['order_id'])
    
    op.create_table(
        'ebay_messages',
        sa.Column('message_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('thread_id', sa.String(100), nullable=True),
        sa.Column('order_id', sa.String(100), nullable=True),
        sa.Column('sender', sa.String(100), nullable=True),
        sa.Column('recipient', sa.String(100), nullable=True),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('message_date', sa.String(100), nullable=True),
        sa.Column('is_read', sa.Boolean(), default=False),
        sa.Column('message_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('message_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_messages_user_id', 'ebay_messages', ['user_id'])
    op.create_index('idx_ebay_messages_thread_id', 'ebay_messages', ['thread_id'])
    
    op.create_table(
        'ebay_offers',
        sa.Column('offer_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('listing_id', sa.String(100), nullable=True),
        sa.Column('buyer_username', sa.String(100), nullable=True),
        sa.Column('offer_amount', sa.Float(), nullable=True),
        sa.Column('offer_currency', sa.String(10), nullable=True),
        sa.Column('offer_status', sa.String(50), nullable=True),
        sa.Column('offer_date', sa.String(100), nullable=True),
        sa.Column('expiration_date', sa.String(100), nullable=True),
        sa.Column('offer_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('offer_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_offers_user_id', 'ebay_offers', ['user_id'])
    op.create_index('idx_ebay_offers_listing_id', 'ebay_offers', ['listing_id'])
    
    op.create_table(
        'ebay_disputes',
        sa.Column('dispute_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('order_id', sa.String(100), nullable=True),
        sa.Column('dispute_reason', sa.Text(), nullable=True),
        sa.Column('dispute_status', sa.String(50), nullable=True),
        sa.Column('open_date', sa.String(100), nullable=True),
        sa.Column('respond_by_date', sa.String(100), nullable=True),
        sa.Column('dispute_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('dispute_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_disputes_user_id', 'ebay_disputes', ['user_id'])
    op.create_index('idx_ebay_disputes_order_id', 'ebay_disputes', ['order_id'])
    
    op.create_table(
        'ebay_cases',
        sa.Column('case_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('order_id', sa.String(100), nullable=True),
        sa.Column('case_type', sa.String(50), nullable=True),
        sa.Column('case_status', sa.String(50), nullable=True),
        sa.Column('open_date', sa.String(100), nullable=True),
        sa.Column('close_date', sa.String(100), nullable=True),
        sa.Column('case_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('case_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_cases_user_id', 'ebay_cases', ['user_id'])
    op.create_index('idx_ebay_cases_order_id', 'ebay_cases', ['order_id'])
    
    op.create_table(
        'ebay_sync_jobs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('sync_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('records_fetched', sa.Integer(), default=0),
        sa.Column('records_stored', sa.Integer(), default=0),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sync_data', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_ebay_sync_jobs_user_id', 'ebay_sync_jobs', ['user_id'])
    op.create_index('idx_ebay_sync_jobs_type', 'ebay_sync_jobs', ['sync_type'])


def downgrade() -> None:
    """Drop eBay data tables"""
    op.drop_table('ebay_sync_jobs')
    op.drop_table('ebay_cases')
    op.drop_table('ebay_disputes')
    op.drop_table('ebay_offers')
    op.drop_table('ebay_messages')
    op.drop_table('ebay_transactions')
    op.drop_table('ebay_orders')
