import os
import json
from sqlalchemy import create_engine, text

def get_database_url():
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    try:
        with open("railway_vars_dump.json", "r", encoding="utf-16") as f:
            data = json.load(f)
            return data.get("DATABASE_URL")
    except Exception:
        return None

def check_table(engine, table_name):
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1"))
        print(f"[OK] Table '{table_name}' exists.")
        return True
    except Exception as e:
        print(f"[MISSING] Table '{table_name}' does not exist or error: {e}")
        return False

def main():
    db_url = get_database_url()
    if not db_url:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    
    tables_to_check = [
        "ebay_orders",
        "orders",
        "purchases",
        "ebay_messages",
        "emails_messages",
        "ebay_transactions",
        "transactions",
        "ebay_offers",
        "offers"
    ]
    
    print("Verifying table existence...")
    for t in tables_to_check:
        check_table(engine, t)

if __name__ == "__main__":
    main()
