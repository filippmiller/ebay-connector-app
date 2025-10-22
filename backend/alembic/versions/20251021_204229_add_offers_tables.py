"""add offers tables

Revision ID: add_offers_001
Revises: enhance_sync_logs_001
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'add_offers_001'
down_revision = 'enhance_sync_logs_001'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'offers',
        sa.Column('offer_id', sa.String(100), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('direction', sa.Enum('INBOUND', 'OUTBOUND', name='offerdirection'), nullable=False),
        sa.Column('state', sa.Enum('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COUNTERED', 'SENT', name='offerstate'), nullable=False, server_default='PENDING'),
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
    
    op.create_table(
        'offer_actions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('offer_id', sa.String(100), sa.ForeignKey('offers.offer_id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.Enum('SEND', 'ACCEPT', 'DECLINE', 'COUNTER', 'EXPIRE', 'WITHDRAW', name='offeraction'), nullable=False),
        sa.Column('actor', sa.Enum('SYSTEM', 'ADMIN', name='offeractor'), nullable=False, server_default='SYSTEM'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('result_state', sa.Enum('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COUNTERED', 'SENT', name='offerstate'), nullable=True),
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
