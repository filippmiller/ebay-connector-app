"""Query TEST inventory record and analyze required fields for eBay listing."""
import os
import json
from sqlalchemy import create_engine, text

# Get DATABASE_URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:2ma5C7qZHXFJJGOG@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    exit(1)

# Connect to database
engine = create_engine(DATABASE_URL)


with engine.connect() as conn:
    # First, get column information
    columns_query = text("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'tbl_parts_inventory'
    ORDER BY ordinal_position
    """)
    
    print("\n" + "="*80)
    print("TABLE STRUCTURE: tbl_parts_inventory")
    print("="*80)
    
    col_result = conn.execute(columns_query)
    columns_list = []
    for col_row in col_result:
        col_name, col_type = col_row
        columns_list.append(col_name)
        print(f"{col_name:40s}: {col_type}")
    
    # Now query the TEST record - looking for status column
    # Based on image, should be id=10
    query = text("""
    SELECT *
    FROM tbl_parts_inventory
    WHERE "ID" = 10
    LIMIT 1
    """)
    
    result = conn.execute(query)
    row = result.fetchone()
    
    if row:
        # Get column names
        columns = result.keys()
        
        # Create dict from row
        record = dict(zip(columns, row))
        
        # Print formatted output
        print("\n" + "="*80)
        print("TEST INVENTORY RECORD (ID=10)")
        print("="*80)
        
        for key, value in sorted(record.items()):
            if value is not None and value != '':
                print(f"{key:40s}: {value}")
        
        print("\n" + "="*80)
        print("EXTRACTING KEY EBAY FIELDS")
        print("="*80)
        
        # Extract SKU and related info
        sku = record.get('SKU')
        print(f"SKU: {sku}")
        
        # Now query SKU table for related data
        if sku:
            sku_query = text("""
            SELECT *
            FROM "SKU_catalog"
            WHERE "SKU" = :sku
            LIMIT 1
            """)
            
            sku_result = conn.execute(sku_query, {"sku": sku})
            sku_row = sku_result.fetchone()
            
            if sku_row:
                sku_cols = sku_result.keys()
                sku_record = dict(zip(sku_cols, sku_row))
                
                print("\n" + "-"*80)
                print("SKU CATALOG RECORD")
                print("-"*80)
                
                for key, value in sorted(sku_record.items()):
                    if value is not None and value != '':
                        print(f"{key:40s}: {value}")
        
        # Query shipping groups
        print("\n" + "-"*80)
        print("SHIPPING GROUPS (Sample)")
        print("-"*80)
        
        ship_query = text("SELECT * FROM tbl_shippinggroups LIMIT 3")
        ship_result = conn.execute(ship_query)
        for idx, ship_row in enumerate(ship_result, 1):
            ship_dict = dict(zip(ship_result.keys(), ship_row))
            print(f"\nShipping Group #{idx}:")
            for k, v in ship_dict.items():
                if v is not None and v != '':
                    print(f"  {k}: {v}")
            
    else:
        print("No record found with ID=10!")

