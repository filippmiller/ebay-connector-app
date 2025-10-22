"""enhance inventory table for production

Revision ID: enhance_inventory_001
Revises: add_offers_001
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'enhance_inventory_001'
down_revision = 'add_offers_001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('inventory', sa.Column('model', sa.Text(), nullable=True))
    op.add_column('inventory', sa.Column('part_number', sa.String(100), nullable=True))
    op.add_column('inventory', sa.Column('price_value', sa.Numeric(14, 2), nullable=True))
    op.add_column('inventory', sa.Column('price_currency', sa.CHAR(3), nullable=True))
    op.add_column('inventory', sa.Column('ebay_listing_id', sa.String(100), nullable=True))
    op.add_column('inventory', sa.Column('ebay_status', sa.Enum('ACTIVE', 'ENDED', 'DRAFT', 'PENDING', 'UNKNOWN', name='ebaystatus'), nullable=True))
    op.add_column('inventory', sa.Column('photo_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('inventory', sa.Column('storage_id', sa.String(100), nullable=True))
    op.add_column('inventory', sa.Column('author', sa.String(100), nullable=True))
    op.add_column('inventory', sa.Column('buyer_info', sa.Text(), nullable=True))
    op.add_column('inventory', sa.Column('tracking_number', sa.String(100), nullable=True))
    op.add_column('inventory', sa.Column('raw_payload', JSONB, nullable=True))
    
    op.create_index('idx_inventory_part_number', 'inventory', ['part_number'])
    op.create_index('idx_inventory_ebay_listing_id', 'inventory', ['ebay_listing_id'])
    op.create_index('idx_inventory_ebay_status', 'inventory', ['ebay_status'])
    op.create_index('idx_inventory_storage_id', 'inventory', ['storage_id'])
    op.create_index('idx_inventory_author', 'inventory', ['author'])
    op.create_index('idx_inventory_tracking_number', 'inventory', ['tracking_number'])
    op.create_index('idx_inventory_rec_created', 'inventory', [sa.text('rec_created DESC')])
    op.create_index('idx_inventory_rec_updated', 'inventory', [sa.text('rec_updated DESC')])
    
    op.execute("""
        CREATE INDEX idx_inventory_title_trgm ON inventory 
        USING gin (title gin_trgm_ops)
    """)

def downgrade():
    op.execute('DROP INDEX IF EXISTS idx_inventory_title_trgm')
    op.drop_index('idx_inventory_rec_updated', table_name='inventory')
    op.drop_index('idx_inventory_rec_created', table_name='inventory')
    op.drop_index('idx_inventory_tracking_number', table_name='inventory')
    op.drop_index('idx_inventory_author', table_name='inventory')
    op.drop_index('idx_inventory_storage_id', table_name='inventory')
    op.drop_index('idx_inventory_ebay_status', table_name='inventory')
    op.drop_index('idx_inventory_ebay_listing_id', table_name='inventory')
    op.drop_index('idx_inventory_part_number', table_name='inventory')
    
    op.drop_column('inventory', 'raw_payload')
    op.drop_column('inventory', 'tracking_number')
    op.drop_column('inventory', 'buyer_info')
    op.drop_column('inventory', 'author')
    op.drop_column('inventory', 'storage_id')
    op.drop_column('inventory', 'photo_count')
    op.drop_column('inventory', 'ebay_status')
    op.drop_column('inventory', 'ebay_listing_id')
    op.drop_column('inventory', 'price_currency')
    op.drop_column('inventory', 'price_value')
    op.drop_column('inventory', 'part_number')
    op.drop_column('inventory', 'model')
    
    op.execute('DROP TYPE ebaystatus')
