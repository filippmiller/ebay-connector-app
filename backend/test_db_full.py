#!/usr/bin/env python3
"""
Full database test - check tables and user_grid_layouts structure.
"""

import os
import sys
import psycopg2
from psycopg2 import sql

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not set")
    sys.exit(1)

conn = psycopg2.connect(db_url, connect_timeout=10)
cur = conn.cursor()

print("="*80)
print("SKU Catalog Table Check")
print("="*80)

# Check for SKU_catalog (quoted name)
try:
    cur.execute('SELECT COUNT(*) FROM "SKU_catalog";')
    count = cur.fetchone()[0]
    print(f"✅ SKU_catalog: {count:,} rows")
except Exception as e:
    print(f"⚠️  SKU_catalog: {e}")

print("\n" + "="*80)
print("user_grid_layouts Structure")
print("="*80)

cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns 
    WHERE table_name = 'user_grid_layouts'
    ORDER BY ordinal_position;
""")
cols = cur.fetchall()
if cols:
    print("Columns in user_grid_layouts:")
    for col_name, col_type, nullable in cols:
        print(f"  - {col_name}: {col_type} (nullable: {nullable})")
else:
    print("⚠️  user_grid_layouts table not found")

print("\n" + "="*80)
print("Sample user_grid_layouts Data")
print("="*80)

cur.execute("SELECT grid_key, user_id, visible_columns, column_widths FROM user_grid_layouts LIMIT 5;")
rows = cur.fetchall()
if rows:
    print(f"Found {len(rows)} layout(s):")
    for row in rows:
        grid_key, user_id, visible_cols, widths = row
        print(f"  - grid_key: {grid_key}, user_id: {user_id[:8]}..., visible: {len(visible_cols) if visible_cols else 0} cols")
else:
    print("No layouts found")

cur.close()
conn.close()
print("\n✅ Test completed")

