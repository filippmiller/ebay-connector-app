#!/usr/bin/env python3
"""Manually test INSERT into tbl_parts_models to find the missing column"""

import psycopg2

conn_str = "postgresql://postgres.nrpfahjygulsfxmbmfzv:2Hu505ZIgaJQECzW@aws-1-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    
    # Try INSERT with minimal data (just model name and all NOT NULL fields)
    sql = """
        INSERT INTO "tbl_parts_models" 
        ("Model", "working", "motherboard", "battery", "hdd", "keyboard", "memory", 
         "screen", "casing", "drive", "damage", "cd", "adapter")
        VALUES 
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING "ID"
    """
    
    values = (
        'Test Model Manual Insert',  # Model
        0,  # working
        0,  # motherboard
        0,  # battery
        0,  # hdd
        0,  # keyboard
        0,  # memory
        0,  # screen
        0,  # casing
        0,  # drive
        0,  # damage
        0,  # cd
        0,  # adapter
    )
    
    cur.execute(sql, values)
    result = cur.fetchone()
    conn.commit()
    
    print(f"✅ SUCCESS! Created model with ID: {result[0]}")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    print(f"\nThis tells us which column is missing!")
    import traceback
    traceback.print_exc()
