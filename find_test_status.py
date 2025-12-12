"""Find status tables and TEST status mapping"""
from sqlalchemy import create_engine, text, inspect

DATABASE_URL = "postgresql://postgres:2ma5C7qZHXFJJGOG@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
engine = create_engine(DATABASE_URL)

print("\n" + "="*100)
print("SEARCHING FOR STATUS TABLES")
print("="*100)

with engine.connect() as conn:
    # Find all tables with 'status' in the name
    query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name ILIKE '%status%'
        ORDER BY table_name
    """)
    
    result = conn.execute(query)
    tables = [row[0] for row in result]
    
    print(f"\nFound {len(tables)} tables with 'status' in name:")
    for table in tables:
        print(f"  - {table}")
    
    # Now search each table for a 'TEST' record
    print("\n" + "="*100)
    print("SEARCHING FOR 'TEST' STATUS")
    print("="*100)
    
    for table in tables:
        print(f"\n>>> Checking table: {table}")
        try:
            # Get columns for this table
            col_query = text(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """)
            col_result = conn.execute(col_query)
            columns = [(row[0], row[1]) for row in col_result]
            
            print(f"    Columns: {', '.join([c[0] for c in columns[:5]])}...")
            
            # Try to find TEST in text columns
            for col_name, col_type in columns:
                if 'char' in col_type.lower() or 'text' in col_type.lower():
                    try:
                        search_query = text(f'SELECT * FROM "{table}" WHERE "{col_name}" ILIKE \'%TEST%\' LIMIT 3')
                        search_result = conn.execute(search_query)
                        rows = search_result.fetchall()
                        
                        if rows:
                            print(f"\n    *** FOUND 'TEST' in column: {col_name} ***")
                            cols = search_result.keys()
                            for row in rows:
                                record = dict(zip(cols, row))
                                print(f"\n    Record:")
                                for k, v in record.items():
                                    if v is not None and v != '':
                                        print(f"      {k}: {v}")
                            break
                    except Exception as e:
                        continue
        except Exception as e:
            print(f"    Error querying {table}: {e}")
            continue
    
    # Also check inventorystatus table specifically (from screenshot)
    print("\n" + "="*100)
    print("CHECKING INVENTORY STATUS TABLES")
    print("="*100)
    
    for table_name in ['tbl_inventorystatus', 'inventorystatus', 'inventory_status']:
        try:
            check_query = text(f'SELECT * FROM "{table_name}" LIMIT 10')
            check_result = conn.execute(check_query)
            print(f"\n>>> Table: {table_name} EXISTS")
            print(f"    Columns: {', '.join(check_result.keys())}")
            
            rows = check_result.fetchall()
            print(f"\n    All records:")
            for row in rows:
                record = dict(zip(check_result.keys(), row))
                print(f"    {record}")
        except Exception as e:
            print(f"\n>>> Table: {table_name} - {str(e)[:100]}")

print("\n" + "="*100)
print("SEARCH COMPLETE")
print("="*100)
