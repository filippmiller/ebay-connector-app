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
    from sqlalchemy import text, inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns and indexes
    inventory_columns = [col['name'] for col in inspector.get_columns('inventory')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('inventory')]
    
    # Add columns only if they don't exist
    if 'model' not in inventory_columns:
        op.add_column('inventory', sa.Column('model', sa.Text(), nullable=True))
    if 'part_number' not in inventory_columns:
        op.add_column('inventory', sa.Column('part_number', sa.String(100), nullable=True))
    if 'price_value' not in inventory_columns:
        op.add_column('inventory', sa.Column('price_value', sa.Numeric(14, 2), nullable=True))
    if 'price_currency' not in inventory_columns:
        op.add_column('inventory', sa.Column('price_currency', sa.CHAR(3), nullable=True))
    if 'ebay_listing_id' not in inventory_columns:
        op.add_column('inventory', sa.Column('ebay_listing_id', sa.String(100), nullable=True))
    if 'ebay_status' not in inventory_columns:
        # Check if ebaystatus ENUM type exists
        result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'ebaystatus'"))
        if result.fetchone() is None:
            conn.execute(text("CREATE TYPE ebaystatus AS ENUM ('ACTIVE', 'ENDED', 'DRAFT', 'PENDING', 'UNKNOWN')"))
            conn.commit()
        from sqlalchemy.dialects.postgresql import ENUM
        ebaystatus_enum = ENUM('ACTIVE', 'ENDED', 'DRAFT', 'PENDING', 'UNKNOWN', name='ebaystatus', create_type=False)
        op.add_column('inventory', sa.Column('ebay_status', ebaystatus_enum, nullable=True))
    if 'photo_count' not in inventory_columns:
        op.add_column('inventory', sa.Column('photo_count', sa.Integer(), nullable=True, server_default='0'))
    if 'storage_id' not in inventory_columns:
        op.add_column('inventory', sa.Column('storage_id', sa.String(100), nullable=True))
    if 'author' not in inventory_columns:
        op.add_column('inventory', sa.Column('author', sa.String(100), nullable=True))
    if 'buyer_info' not in inventory_columns:
        op.add_column('inventory', sa.Column('buyer_info', sa.Text(), nullable=True))
    if 'tracking_number' not in inventory_columns:
        op.add_column('inventory', sa.Column('tracking_number', sa.String(100), nullable=True))
    if 'raw_payload' not in inventory_columns:
        op.add_column('inventory', sa.Column('raw_payload', JSONB, nullable=True))
    
    # Create indexes only if they don't exist
    if 'idx_inventory_part_number' not in existing_indexes:
        op.create_index('idx_inventory_part_number', 'inventory', ['part_number'])
    if 'idx_inventory_ebay_listing_id' not in existing_indexes:
        op.create_index('idx_inventory_ebay_listing_id', 'inventory', ['ebay_listing_id'])
    if 'idx_inventory_ebay_status' not in existing_indexes:
        op.create_index('idx_inventory_ebay_status', 'inventory', ['ebay_status'])
    if 'idx_inventory_storage_id' not in existing_indexes:
        op.create_index('idx_inventory_storage_id', 'inventory', ['storage_id'])
    if 'idx_inventory_author' not in existing_indexes:
        op.create_index('idx_inventory_author', 'inventory', ['author'])
    if 'idx_inventory_tracking_number' not in existing_indexes:
        op.create_index('idx_inventory_tracking_number', 'inventory', ['tracking_number'])
    if 'idx_inventory_rec_created' not in existing_indexes:
        op.create_index('idx_inventory_rec_created', 'inventory', [sa.text('rec_created DESC')])
    if 'idx_inventory_rec_updated' not in existing_indexes:
        op.create_index('idx_inventory_rec_updated', 'inventory', [sa.text('rec_updated DESC')])
    
    # Only create title index if title column exists
    if 'title' in inventory_columns and 'idx_inventory_title_trgm' not in existing_indexes:
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
