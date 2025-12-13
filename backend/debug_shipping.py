import os
from sqlalchemy import create_engine, text

def test_shipping_groups():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return

    # Mask password for logging
    safe_url = db_url
    if "@" in safe_url:
        safe_url = safe_url.split("@")[-1]
    print(f"Connecting to ...@{safe_url}") 
    
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            print("Connected successfully!\n")
            
            # Check tbl_internalshippinggroups
            print("--- Checking \"tbl_internalshippinggroups\" ---")
            try:
                result = conn.execute(text('SELECT COUNT(*) FROM "tbl_internalshippinggroups"'))
                count = result.scalar()
                print(f"Total count: {count}")
                
                if count > 0:
                    result = conn.execute(text('SELECT * FROM "tbl_internalshippinggroups" LIMIT 1'))
                    print(f"Columns: {result.keys()}")
                    for row in result:
                        print(f"Sample row: {row}")
                    
                    # Check active records
                    result = conn.execute(text('SELECT COUNT(*) FROM "tbl_internalshippinggroups" WHERE "Active" = true'))
                    active_count = result.scalar()
                    print(f"\nActive records (Active=true): {active_count}")
                    
                    # Show all records with their Active status
                    result = conn.execute(text('SELECT "ID", "Name", "Active" FROM "tbl_internalshippinggroups" ORDER BY "ID"'))
                    print("\nAll records:")
                    for row in result:
                        print(f"  ID={row[0]}, Name={row[1]}, Active={row[2]}")
                        
            except Exception as e:
                print(f"Error: {e}")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_shipping_groups()
