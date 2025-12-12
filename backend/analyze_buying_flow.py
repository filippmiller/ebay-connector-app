"""
Analyze Buying-to-Fees Data Flow
=================================

This script queries the Supabase database to:
1. List all existing tables
2. Compare with tables mentioned in the friend's analytics
3. Identify missing tables
4. Explain the data flow from Buying → Inventory → Sales → Transactions → Fees
"""

from sqlalchemy import text
from app.models_sqlalchemy import engine as pg_engine

# Tables mentioned in friend's SQL analysis
MSSQL_TABLES = [
    "tbl_parts_Inventory",
    "tbl_parts_Inventory_detail",
    "tbl_ListingFees",
    "tbl_ebay_InventorySold",
    "tbl_ebay_seller_info",
    "tbl_ebay_SellerTransactions",
    "tbl_ebay_fees",
    "tbl_stock_info",
    "tbl_parcel_statistics",
    "tbl_dev_keys_statistics",
]


def get_supabase_tables():
    """Get all tables from Supabase public schema."""
    with pg_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """))
        return [row[0] for row in result]


def main():
    print("=" * 80)
    print("ANALYZING BUYING-TO-FEES DATA FLOW")
    print("=" * 80)
    print()
    
    # Get all Supabase tables
    print("[*] Querying Supabase database...")
    supabase_tables = get_supabase_tables()
    print(f"[OK] Found {len(supabase_tables)} tables in Supabase\n")
    
    print("=" * 80)
    print("ALL SUPABASE TABLES")
    print("=" * 80)
    for i, table in enumerate(supabase_tables, 1):
        print(f"{i:3d}. {table}")
    print()
    
    # Compare with MSSQL tables
    print("=" * 80)
    print("TABLES MENTIONED IN FRIEND'S ANALYSIS (MSSQL)")
    print("=" * 80)
    
    # Convert to lowercase for case-insensitive comparison
    supabase_tables_lower = {t.lower() for t in supabase_tables}
    
    missing_tables = []
    existing_tables = []
    
    for table in MSSQL_TABLES:
        table_name = table.replace("dbo.", "")
        if table_name.lower() in supabase_tables_lower:
            status = "[OK] EXISTS"
            existing_tables.append(table_name)
        else:
            status = "[X] MISSING"
            missing_tables.append(table_name)
        
        print(f"{status:12s} {table}")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"[OK] Existing in Supabase: {len(existing_tables)}")
    print(f"[X]  Missing in Supabase:  {len(missing_tables)}")
    print()
    
    if missing_tables:
        print("Missing tables:")
        for table in missing_tables:
            print(f"  - {table}")
        print()
    
    # Explain the data flow
    print("=" * 80)
    print("DATA FLOW EXPLANATION: FROM BUYING TO FEES")
    print("=" * 80)
    print()
    print("Based on your friend's analysis, here's the data flow chain:")
    print()
    print("[1] BUYING PROCESS (Computer Purchase)")
    print("    --> Creates record somewhere (tbl_buying? tbl_buyiner?)")
    print()
    print("[2] INVENTORY")
    print("    --> tbl_parts_Inventory (ID, SKU, Storage, StorageID)")
    print("    --> tbl_parts_Inventory_detail (detailed info, might be 1:1 or 1:many)")
    print()
    print("[3] LISTING FEES (Before Sale)")
    print("    --> tbl_ListingFees (InventoryID -> insertion fees, listing fees)")
    print()
    print("[4] SALE EVENT")
    print("    --> tbl_ebay_InventorySold")
    print("        - Links: InventoryID, TransactionID, OrderLineItemID")
    print("        - This is the JUNCTION table between Inventory and Sales")
    print()
    print("[5] TRANSACTION DETAILS")
    print("    --> tbl_ebay_SellerTransactions")
    print("        - Keys: TransactionID, OrderLineItemID, OrderID")
    print("        - Data: prices, amounts (TransactionPrice, AmountPaid)")
    print()
    print("    --> tbl_ebay_seller_info")
    print("        - Keys: same as above")
    print("        - Data: buyer info, sales record number")
    print()
    print("[6] SELLING FEES (After Sale)")
    print("    --> tbl_ebay_fees")
    print("        - Links via: TransactionID and/or OrderLineItemID")
    print("        - Data: FinalValueFee, FixedFee, etc.")
    print()
    print("[*] KEY RELATIONSHIPS:")
    print("   - InventoryID connects Buying -> Inventory -> Sales -> Fees (via Listing)")
    print("   - TransactionID connects Sales -> Transaction Details -> Selling Fees")
    print("   - OrderLineItemID is an alternative key used across multiple tables")
    print()
    print("[!] YOUR FRIEND'S SQL QUERY LOGIC:")
    print("   1. Start with InventoryID (e.g., 469270)")
    print("   2. Find all sales in tbl_ebay_InventorySold")
    print("   3. Join to tbl_ebay_SellerTransactions via TransactionID")
    print("   4. Join to tbl_ebay_seller_info via TransactionID (buyer details)")
    print("   5. Sum up tbl_ebay_fees via TransactionID (selling commissions)")
    print("   6. Sum up tbl_ListingFees via InventoryID (listing costs)")
    print("   7. Result: Complete P&L for one inventory item from buying to all fees")
    print()
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
