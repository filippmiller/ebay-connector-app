import os
from sqlalchemy import create_engine, text

def check_duplicates():
    db_url = os.environ.get("DATABASE_URL")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Check for duplicate IDs
        result = conn.execute(text('''
            SELECT "ID", "Name", COUNT(*) as count
            FROM "tbl_internalshippinggroups"
            GROUP BY "ID", "Name"
            HAVING COUNT(*) > 1
        '''))
        
        duplicates = result.fetchall()
        
        if duplicates:
            print("Found duplicates:")
            for row in duplicates:
                print(f"  ID={row[0]}, Name={row[1]}, Count={row[2]}")
        else:
            print("No duplicates found")
        
        # Check primary key
        result = conn.execute(text('''
            SELECT
                tc.constraint_name, tc.constraint_type,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'tbl_internalshippinggroups'
              AND tc.constraint_type = 'PRIMARY KEY'
        '''))
        
        pk = result.fetchall()
        if pk:
            print("\nPrimary key:")
            for row in pk:
                print(f"  {row}")
        else:
            print("\nNo primary key found!")
        
        # Show all unique records
        result = conn.execute(text('''
            SELECT DISTINCT "ID", "Name", "Active"
            FROM "tbl_internalshippinggroups"
            ORDER BY "ID"
        '''))
        
        print("\nDISTINCT records:")
        for row in result:
            print(f"  ID={row[0]}, Name={row[1]}, Active={row[2]}")

if __name__ == "__main__":
    check_duplicates()
