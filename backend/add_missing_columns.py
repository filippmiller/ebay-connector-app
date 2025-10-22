"""
Directly add missing normalized columns to Postgres
"""
import os
os.environ['DATABASE_URL'] = 'postgresql://postgres:EVfiVxDuuwRa8hAx@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require'

from sqlalchemy import create_engine, text, inspect
from app.config import settings

def add_columns():
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    
    if 'ebay_orders' not in inspector.get_table_names():
        print("❌ ebay_orders table not found!")
        return
    
    existing = {col['name'] for col in inspector.get_columns('ebay_orders')}
    print(f"✅ Found ebay_orders with {len(existing)} columns")
    print(f"📋 Existing: {sorted(existing)}")
    
    columns_to_add = [
        ("buyer_registered", "VARCHAR(100)"),
        ("order_total_value", "NUMERIC(14,2)"),
        ("order_total_currency", "CHAR(3)"),
        ("line_items_count", "INTEGER DEFAULT 0"),
        ("tracking_number", "VARCHAR(100)"),
        ("ship_to_name", "VARCHAR(255)"),
        ("ship_to_city", "VARCHAR(100)"),
        ("ship_to_state", "VARCHAR(100)"),
        ("ship_to_postal_code", "VARCHAR(20)"),
        ("ship_to_country_code", "CHAR(2)"),
        ("raw_payload", "TEXT"),
    ]
    
    with engine.connect() as conn:
        for col_name, col_type in columns_to_add:
            if col_name not in existing:
                sql = f"ALTER TABLE ebay_orders ADD COLUMN {col_name} {col_type}"
                print(f"➕ Adding column: {col_name}")
                conn.execute(text(sql))
                conn.commit()
            else:
                print(f"⏭️  Column exists: {col_name}")
        
        # Create line_items table
        if 'order_line_items' not in inspector.get_table_names():
            print("➕ Creating order_line_items table")
            conn.execute(text("""
                CREATE TABLE order_line_items (
                    id BIGSERIAL PRIMARY KEY,
                    order_id VARCHAR(100) NOT NULL,
                    line_item_id VARCHAR(100) NOT NULL,
                    sku VARCHAR(100),
                    title TEXT,
                    quantity INTEGER DEFAULT 0,
                    total_value NUMERIC(14,2),
                    currency CHAR(3),
                    raw_payload TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(order_id, line_item_id)
                )
            """))
            conn.execute(text("CREATE INDEX idx_line_items_order_id ON order_line_items(order_id)"))
            conn.commit()
        else:
            print("⏭️  order_line_items table exists")
    
    print("✅ All columns added successfully!")

if __name__ == "__main__":
    add_columns()
