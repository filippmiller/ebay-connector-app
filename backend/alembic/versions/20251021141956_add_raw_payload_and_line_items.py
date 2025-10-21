"""add raw_payload and order_line_items table

Revision ID: add_raw_payload_line_items
Revises: d6c1e7ca5b83
Create Date: 2025-10-21 14:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_raw_payload_line_items'
down_revision = 'd6c1e7ca5b83'
branch_labels = None
depends_on = None


def upgrade():
    # Add raw_payload column to ebay_orders if not exists
    op.execute("""
        ALTER TABLE ebay_orders 
        ADD COLUMN IF NOT EXISTS raw_payload JSONB;
    """)
    
    # Add additional normalized columns
    op.execute("""
        ALTER TABLE ebay_orders 
        ADD COLUMN IF NOT EXISTS order_total_value NUMERIC(14,2),
        ADD COLUMN IF NOT EXISTS order_total_currency CHAR(3),
        ADD COLUMN IF NOT EXISTS line_items_count INT DEFAULT 0,
        ADD COLUMN IF NOT EXISTS buyer_registered BOOLEAN,
        ADD COLUMN IF NOT EXISTS tracking_number TEXT,
        ADD COLUMN IF NOT EXISTS ship_to_name TEXT,
        ADD COLUMN IF NOT EXISTS ship_to_city TEXT,
        ADD COLUMN IF NOT EXISTS ship_to_state TEXT,
        ADD COLUMN IF NOT EXISTS ship_to_postal_code TEXT,
        ADD COLUMN IF NOT EXISTS ship_to_country_code CHAR(2);
    """)
    
    # Create order_line_items table
    op.execute("""
        CREATE TABLE IF NOT EXISTS order_line_items (
            id BIGSERIAL PRIMARY KEY,
            order_id TEXT NOT NULL,
            line_item_id TEXT,
            sku TEXT,
            title TEXT,
            quantity INT DEFAULT 0,
            total_value NUMERIC(14,2),
            currency CHAR(3),
            raw_payload JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT fk_order
                FOREIGN KEY(order_id) 
                REFERENCES ebay_orders(order_id)
                ON DELETE CASCADE,
            CONSTRAINT unique_order_line_item UNIQUE(order_id, line_item_id)
        );
    """)
    
    # Create indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_line_items_order_id ON order_line_items(order_id);
        CREATE INDEX IF NOT EXISTS idx_line_items_sku ON order_line_items(sku);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS order_line_items CASCADE;")
    op.execute("""
        ALTER TABLE ebay_orders 
        DROP COLUMN IF EXISTS raw_payload,
        DROP COLUMN IF EXISTS order_total_value,
        DROP COLUMN IF EXISTS order_total_currency,
        DROP COLUMN IF EXISTS line_items_count,
        DROP COLUMN IF EXISTS buyer_registered,
        DROP COLUMN IF EXISTS tracking_number,
        DROP COLUMN IF EXISTS ship_to_name,
        DROP COLUMN IF EXISTS ship_to_city,
        DROP COLUMN IF EXISTS ship_to_state,
        DROP COLUMN IF EXISTS ship_to_postal_code,
        DROP COLUMN IF EXISTS ship_to_country_code;
    """)
