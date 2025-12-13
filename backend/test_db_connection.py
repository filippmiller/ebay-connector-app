#!/usr/bin/env python3
"""
Test script to verify database connection to Supabase/Postgres.

This script:
1. Checks if DATABASE_URL is set
2. Attempts to connect to the database
3. Queries a simple table to verify connectivity
4. Lists some grid-related tables and their row counts
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_connection():
    """Test database connection."""
    print("="*80)
    print("Database Connection Test")
    print("="*80)
    
    # Check DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL is not set")
        print("   Cannot connect to database without DATABASE_URL")
        return False
    
    print(f"✅ DATABASE_URL is set (length: {len(db_url)})")
    print(f"   Starts with postgres: {db_url.startswith('postgres')}")
    print(f"   Contains supabase: {'supabase' in db_url.lower()}")
    
    # Try to import and connect
    try:
        import psycopg2
        from psycopg2 import sql
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return False
    
    try:
        print("\nAttempting to connect to database...")
        conn = psycopg2.connect(db_url, connect_timeout=10)
        print("✅ Successfully connected to database")
        
        cur = conn.cursor()
        
        # Get database version
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"\n📊 Database version: {version[:80]}...")
        
        # Test query - check if we can read from a simple table
        print("\nTesting basic query...")
        cur.execute("SELECT 1 as test;")
        result = cur.fetchone()
        print(f"✅ Basic query works: {result}")
        
        # Check for grid-related tables
        print("\n" + "="*80)
        print("Checking Grid-Related Tables")
        print("="*80)
        
        grid_tables = [
            "order_line_items",
            "ebay_transactions",
            "ebay_finances_transactions",
            "ebay_finances_fees",
            "ebay_buyer",
            "ebay_active_inventory",
            "tbl_parts_inventory",
            "offers",
            "user_grid_layouts",
            "sku_catalog",
            "sq_items",
        ]
        
        for table_name in grid_tables:
            try:
                # Check if table exists and get row count
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        sql.Identifier(table_name)
                    )
                )
                count = cur.fetchone()[0]
                print(f"✅ {table_name}: {count:,} rows")
            except Exception as e:
                # Table might not exist or be in different schema
                print(f"⚠️  {table_name}: {str(e)[:60]}")
        
        # Check user_grid_layouts structure
        print("\n" + "="*80)
        print("Checking user_grid_layouts table structure")
        print("="*80)
        try:
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'user_grid_layouts'
                ORDER BY ordinal_position;
            """)
            cols = cur.fetchall()
            if cols:
                print("Columns in user_grid_layouts:")
                for col_name, col_type in cols:
                    print(f"  - {col_name}: {col_type}")
            else:
                print("⚠️  user_grid_layouts table not found or has no columns")
        except Exception as e:
            print(f"⚠️  Could not check user_grid_layouts structure: {e}")
        
        cur.close()
        conn.close()
        print("\n✅ Database connection test completed successfully")
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

