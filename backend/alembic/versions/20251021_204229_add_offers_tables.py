"""add offers tables

Revision ID: add_offers_001
Revises: enhance_sync_logs_001
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM

revision = 'add_offers_001'
down_revision = 'enhance_sync_logs_001'
branch_labels = None
depends_on = None

def upgrade():
    # Create ENUM types if they don't exist
    from sqlalchemy import text
    conn = op.get_bind()
    
    # Check and create offerdirection type
    result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'offerdirection'"))
    if result.fetchone() is None:
        conn.execute(text("CREATE TYPE offerdirection AS ENUM ('INBOUND', 'OUTBOUND')"))
        conn.commit()
    
    # Check and create offerstate type
    result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'offerstate'"))
    if result.fetchone() is None:
        conn.execute(text("CREATE TYPE offerstate AS ENUM ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COUNTERED', 'SENT')"))
        conn.commit()
    
    # Check and create offeraction type
    result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'offeraction'"))
    if result.fetchone() is None:
        conn.execute(text("CREATE TYPE offeraction AS ENUM ('SEND', 'ACCEPT', 'DECLINE', 'COUNTER', 'EXPIRE', 'WITHDRAW')"))
        conn.commit()
    
    # Check and create offeractor type
    result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'offeractor'"))
    if result.fetchone() is None:
        conn.execute(text("CREATE TYPE offeractor AS ENUM ('SYSTEM', 'ADMIN')"))
        conn.commit()
    
    # Use postgresql.ENUM with create_type=False to prevent auto-creation
    offerdirection_enum = ENUM('INBOUND', 'OUTBOUND', name='offerdirection', create_type=False)
    offerstate_enum = ENUM('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COUNTERED', 'SENT', name='offerstate', create_type=False)
    offeraction_enum = ENUM('SEND', 'ACCEPT', 'DECLINE', 'COUNTER', 'EXPIRE', 'WITHDRAW', name='offeraction', create_type=False)
    offeractor_enum = ENUM('SYSTEM', 'ADMIN', name='offeractor', create_type=False)
    
    # Check if tables already exist before creating
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'offers' not in existing_tables:
        op.create_table(
            'offers',
            sa.Column('offer_id', sa.String(100), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('direction', offerdirection_enum, nullable=False),
            sa.Column('state', offerstate_enum, nullable=False, server_default='PENDING'),
            sa.Column('item_id', sa.String(100), nullable=True),
            sa.Column('sku', sa.String(100), nullable=True),
            sa.Column('buyer_username', sa.String(100), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=True, server_default='1'),
            sa.Column('price_value', sa.Numeric(14, 2), nullable=True),
            sa.Column('price_currency', sa.CHAR(3), nullable=True),
            sa.Column('original_price_value', sa.Numeric(14, 2), nullable=True),
            sa.Column('original_price_currency', sa.CHAR(3), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('message', sa.Text(), nullable=True),
            sa.Column('raw_payload', JSONB, nullable=True),
        )
        
        op.create_index('idx_offer_item_id', 'offers', ['item_id'])
        op.create_index('idx_offer_state', 'offers', ['state'])
        op.create_index('idx_offer_direction', 'offers', ['direction'])
        op.create_index('idx_offer_created_at', 'offers', ['created_at'])
        op.create_index('idx_offer_buyer', 'offers', ['buyer_username'])
        op.create_index('idx_offer_sku', 'offers', ['sku'])
        op.create_index('idx_offer_user_id', 'offers', ['user_id'])
    
    if 'offer_actions' not in existing_tables:
        op.create_table(
            'offer_actions',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('offer_id', sa.String(100), sa.ForeignKey('offers.offer_id', ondelete='CASCADE'), nullable=False),
            sa.Column('action', offeraction_enum, nullable=False),
            sa.Column('actor', offeractor_enum, nullable=False, server_default='SYSTEM'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('result_state', offerstate_enum, nullable=True),
            sa.Column('raw_payload', JSONB, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        
        op.create_index('idx_offer_action_offer_id', 'offer_actions', ['offer_id'])
        op.create_index('idx_offer_action_created_at', 'offer_actions', ['created_at'])


def downgrade():
    op.drop_index('idx_offer_action_created_at', table_name='offer_actions')
    op.drop_index('idx_offer_action_offer_id', table_name='offer_actions')
    op.drop_table('offer_actions')
    
    op.drop_index('idx_offer_user_id', table_name='offers')
    op.drop_index('idx_offer_sku', table_name='offers')
    op.drop_index('idx_offer_buyer', table_name='offers')
    op.drop_index('idx_offer_created_at', table_name='offers')
    op.drop_index('idx_offer_direction', table_name='offers')
    op.drop_index('idx_offer_state', table_name='offers')
    op.drop_index('idx_offer_item_id', table_name='offers')
    op.drop_table('offers')
    
    op.execute('DROP TYPE offeractor')
    op.execute('DROP TYPE offeraction')
    op.execute('DROP TYPE offerstate')
    op.execute('DROP TYPE offerdirection')
