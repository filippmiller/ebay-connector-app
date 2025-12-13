import os
from sqlalchemy import create_engine, text

def test_connection():
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
            print("Connected successfully!")
            
            # Check tbl_parts_category (quoted, case sensitive)
            print("\n--- Checking \"tbl_parts_category\" ---")
            try:
                result = conn.execute(text('SELECT COUNT(*) FROM "tbl_parts_category"'))
                count = result.scalar()
                print(f"Count: {count}")
                
                if count > 0:
                    result = conn.execute(text('SELECT * FROM "tbl_parts_category" LIMIT 1'))
                    print(f"Columns: {result.keys()}")
                    for row in result:
                        print(row)
            except Exception as e:
                print(f"Error: {e}")
                
            # Check public.tbl_parts_category
            print("\n--- Checking public.\"tbl_parts_category\" ---")
            try:
                result = conn.execute(text('SELECT COUNT(*) FROM public."tbl_parts_category"'))
                count = result.scalar()
                print(f"Count: {count}")
            except Exception as e:
                print(f"Error: {e}")

            # Check if maybe it's lowercase
            print("\n--- Checking tbl_parts_category (lowercase, unquoted) ---")
            try:
                result = conn.execute(text('SELECT COUNT(*) FROM tbl_parts_category'))
                count = result.scalar()
                print(f"Count: {count}")
            except Exception as e:
                print(f"Error: {e}")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_connection()
