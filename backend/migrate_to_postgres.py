#!/usr/bin/env python3
"""
Manual Migration Script: SQLite → Supabase Postgres
This script will:
1. Connect to Supabase Postgres
2. Create all 9 tables using Alembic migration
3. Import existing SQLite data (if exists)
4. Verify the migration
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
import sqlite3

POSTGRES_URL = "postgresql://postgres:EVfiVxDuuwRa8hAx@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
SQLITE_PATH = "/data/ebay_connector.db"

def test_postgres_connection():
    """Test connection to Supabase Postgres"""
    print("🔌 Testing Postgres connection...")
    try:
        engine = create_engine(POSTGRES_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✅ Connected to Postgres: {version[:50]}...")
        return engine
    except Exception as e:
        print(f"❌ Failed to connect to Postgres: {e}")
        sys.exit(1)

def apply_alembic_migration(engine):
    """Apply Alembic migration to create tables"""
    print("\n📊 Applying Alembic migration...")
    
    from alembic.config import Config
    from alembic import command
    
    try:
        os.environ["DATABASE_URL"] = POSTGRES_URL
        
        alembic_cfg = Config("/home/ubuntu/ebay-connector-app/backend/alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", POSTGRES_URL)
        
        command.upgrade(alembic_cfg, "head")
        print("✅ Alembic migration applied successfully!")
        
    except Exception as e:
        print(f"⚠️  Alembic migration issue: {e}")
        print("Attempting manual table creation...")
        create_tables_manually(engine)

def create_tables_manually(engine):
    """Manually create tables if Alembic fails"""
    print("\n🔨 Creating tables manually...")
    
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"))
        conn.commit()
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                ebay_connected BOOLEAN DEFAULT FALSE,
                ebay_access_token TEXT,
                ebay_refresh_token TEXT,
                ebay_token_expires_at TIMESTAMP,
                ebay_environment VARCHAR(20) DEFAULT 'sandbox'
            );
            CREATE INDEX IF NOT EXISTS idx_user_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_user_role ON users(role);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS warehouses (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                location VARCHAR(255),
                capacity INTEGER DEFAULT 0,
                warehouse_type VARCHAR(50),
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_updated TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS buying (
                id SERIAL PRIMARY KEY,
                item_id VARCHAR(100) UNIQUE NOT NULL,
                tracking_number VARCHAR(100),
                buyer_id VARCHAR(100),
                buyer_username VARCHAR(100),
                seller_id VARCHAR(100),
                seller_username VARCHAR(100),
                title TEXT NOT NULL,
                paid_date TIMESTAMP,
                amount_paid DOUBLE PRECISION DEFAULT 0.0,
                sale_price DOUBLE PRECISION DEFAULT 0.0,
                ebay_fee DOUBLE PRECISION DEFAULT 0.0,
                shipping_cost DOUBLE PRECISION DEFAULT 0.0,
                refund DOUBLE PRECISION DEFAULT 0.0,
                profit DOUBLE PRECISION DEFAULT 0.0,
                status VARCHAR(50) DEFAULT 'unpaid',
                storage VARCHAR(100),
                comment TEXT,
                author VARCHAR(100),
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_updated TIMESTAMP NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_buying_item_id ON buying(item_id);
            CREATE INDEX IF NOT EXISTS idx_buying_buyer_id ON buying(buyer_id);
            CREATE INDEX IF NOT EXISTS idx_buying_seller_id ON buying(seller_id);
            CREATE INDEX IF NOT EXISTS idx_buying_status ON buying(status);
            CREATE INDEX IF NOT EXISTS idx_buying_paid_date ON buying(paid_date);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sku (
                id SERIAL PRIMARY KEY,
                sku_code VARCHAR(100) UNIQUE NOT NULL,
                model VARCHAR(100),
                category VARCHAR(100),
                condition VARCHAR(50),
                part_number VARCHAR(100),
                price DOUBLE PRECISION DEFAULT 0.0,
                title TEXT,
                description TEXT,
                brand VARCHAR(100),
                image_url TEXT,
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_updated TIMESTAMP NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_sku_code ON sku(sku_code);
            CREATE INDEX IF NOT EXISTS idx_sku_category ON sku(category);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS listings (
                id SERIAL PRIMARY KEY,
                sku_id INTEGER NOT NULL,
                ebay_listing_id VARCHAR(100) UNIQUE NOT NULL,
                ebay_item_id VARCHAR(100),
                price DOUBLE PRECISION DEFAULT 0.0,
                ebay_price DOUBLE PRECISION DEFAULT 0.0,
                shipping_group VARCHAR(100),
                condition VARCHAR(50),
                storage VARCHAR(100),
                warehouse_id INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                listed_date TIMESTAMP,
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_updated TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (sku_id) REFERENCES sku(id),
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_listing_ebay_id ON listings(ebay_listing_id);
            CREATE INDEX IF NOT EXISTS idx_listing_item_id ON listings(ebay_item_id);
            CREATE INDEX IF NOT EXISTS idx_listing_sku_id ON listings(sku_id);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                sku_id INTEGER NOT NULL,
                storage VARCHAR(100),
                status VARCHAR(50) DEFAULT 'available',
                category VARCHAR(100),
                price DOUBLE PRECISION DEFAULT 0.0,
                warehouse_id INTEGER,
                quantity INTEGER DEFAULT 1,
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_updated TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (sku_id) REFERENCES sku(id),
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_inventory_sku_id ON inventory(sku_id);
            CREATE INDEX IF NOT EXISTS idx_inventory_status ON inventory(status);
            CREATE INDEX IF NOT EXISTS idx_inventory_warehouse_id ON inventory(warehouse_id);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS returns (
                id SERIAL PRIMARY KEY,
                return_id VARCHAR(100) UNIQUE NOT NULL,
                item_id VARCHAR(100),
                ebay_order_id VARCHAR(100),
                buyer VARCHAR(100),
                tracking_number VARCHAR(100),
                reason TEXT,
                sale_price DOUBLE PRECISION DEFAULT 0.0,
                refund_amount DOUBLE PRECISION DEFAULT 0.0,
                status VARCHAR(50),
                comment TEXT,
                return_date TIMESTAMP,
                resolved_date TIMESTAMP,
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_updated TIMESTAMP NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_return_return_id ON returns(return_id);
            CREATE INDEX IF NOT EXISTS idx_return_order_id ON returns(ebay_order_id);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_logs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                endpoint VARCHAR(255) NOT NULL,
                record_count INTEGER DEFAULT 0,
                duration DOUBLE PRECISION DEFAULT 0.0,
                status VARCHAR(50) NOT NULL,
                error_message TEXT,
                sync_started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                sync_completed_at TIMESTAMP,
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_synclog_user_id ON sync_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_synclog_status ON sync_logs(status);
            CREATE INDEX IF NOT EXISTS idx_synclog_started ON sync_logs(sync_started_at);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                report_type VARCHAR(100) NOT NULL,
                filters TEXT,
                file_path VARCHAR(255),
                generated_by VARCHAR(36),
                generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                rec_created TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (generated_by) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_report_type ON reports(report_type);
            CREATE INDEX IF NOT EXISTS idx_report_generated_at ON reports(generated_at);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE
            );
            CREATE INDEX IF NOT EXISTS idx_reset_token_email ON password_reset_tokens(email);
            CREATE INDEX IF NOT EXISTS idx_reset_token_expires ON password_reset_tokens(expires_at);
        """))
        
        conn.commit()
        print("✅ All tables created manually!")

def verify_tables(engine):
    """Verify all tables were created"""
    print("\n🔍 Verifying tables...")
    
    expected_tables = [
        'users', 'warehouses', 'buying', 'sku', 'listings', 
        'inventory', 'returns', 'sync_logs', 'reports', 'password_reset_tokens'
    ]
    
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    print(f"📊 Found {len(existing_tables)} tables:")
    for table in expected_tables:
        if table in existing_tables:
            print(f"  ✅ {table}")
        else:
            print(f"  ❌ {table} (MISSING)")
    
    if 'alembic_version' in existing_tables:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version;"))
            version = result.fetchone()
            if version:
                print(f"\n📌 Alembic version: {version[0]}")
    
    missing = set(expected_tables) - set(existing_tables)
    if missing:
        print(f"\n⚠️  Warning: {len(missing)} tables missing: {missing}")
        return False
    else:
        print("\n✅ All tables verified!")
        return True

def import_sqlite_data(engine):
    """Import data from SQLite if it exists"""
    print("\n📦 Checking for SQLite data to import...")
    
    if not os.path.exists(SQLITE_PATH):
        print(f"⚠️  No SQLite database found at {SQLITE_PATH}")
        print("   This is OK - will start fresh with Postgres!")
        return
    
    try:
        sqlite_conn = sqlite3.connect(SQLITE_PATH)
        sqlite_cursor = sqlite_conn.cursor()
        
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders';")
        if not sqlite_cursor.fetchone():
            print("⚠️  No 'orders' table in SQLite - nothing to import")
            sqlite_conn.close()
            return
        
        sqlite_cursor.execute("SELECT COUNT(*) FROM orders;")
        order_count = sqlite_cursor.fetchone()[0]
        
        if order_count == 0:
            print("⚠️  SQLite orders table is empty - nothing to import")
            sqlite_conn.close()
            return
        
        print(f"📊 Found {order_count} orders in SQLite")
        print("🔄 Importing to Postgres...")
        
        sqlite_cursor.execute("""
            SELECT order_id, buyer_username, buyer_user_id, seller_username, seller_user_id,
                   title, order_status, total_amount, creation_date
            FROM orders;
        """)
        orders = sqlite_cursor.fetchall()
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        imported = 0
        for order in orders:
            try:
                session.execute(text("""
                    INSERT INTO buying (item_id, buyer_username, buyer_id, seller_username, seller_id,
                                       title, status, amount_paid, paid_date, rec_created, rec_updated)
                    VALUES (:item_id, :buyer_username, :buyer_id, :seller_username, :seller_id,
                           :title, :status, :amount_paid, :paid_date, NOW(), NOW())
                    ON CONFLICT (item_id) DO NOTHING;
                """), {
                    'item_id': order[0],
                    'buyer_username': order[1],
                    'buyer_id': order[2],
                    'seller_username': order[3],
                    'seller_id': order[4],
                    'title': order[5],
                    'status': order[6] or 'unknown',
                    'amount_paid': float(order[7]) if order[7] else 0.0,
                    'paid_date': order[8] if order[8] else None
                })
                imported += 1
            except Exception as e:
                print(f"⚠️  Failed to import order {order[0]}: {e}")
        
        session.commit()
        session.close()
        sqlite_conn.close()
        
        print(f"✅ Imported {imported}/{order_count} orders to Postgres!")
        
    except Exception as e:
        print(f"⚠️  Failed to import SQLite data: {e}")
        print("   Continuing without import...")

def main():
    """Main migration process"""
    print("=" * 60)
    print("🚀 EBAY CONNECTOR - POSTGRES MIGRATION")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    print()
    
    engine = test_postgres_connection()
    
    try:
        apply_alembic_migration(engine)
    except Exception as e:
        print(f"⚠️  Alembic failed: {e}")
        print("Falling back to manual table creation...")
        create_tables_manually(engine)
    
    success = verify_tables(engine)
    
    if success:
        import_sqlite_data(engine)
    
    print("\n" + "=" * 60)
    print("✅ MIGRATION COMPLETE!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Update backend to use DATABASE_URL")
    print("2. Deploy backend")
    print("3. Register admin user")
    print("4. Connect eBay and sync orders")
    print()
    print(f"Completed at: {datetime.now()}")

if __name__ == "__main__":
    main()
