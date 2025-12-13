from sqlalchemy import create_engine, inspect
from app.config import settings
import sys

def check_table():
    print(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    if inspector.has_table("ebay_orders"):
        print("Table 'ebay_orders' EXISTS.")
        columns = inspector.get_columns("ebay_orders")
        print(f"Columns: {[c['name'] for c in columns]}")
        indexes = inspector.get_indexes("ebay_orders")
        print(f"Indexes: {[i['name'] for i in indexes]}")
    else:
        print("Table 'ebay_orders' DOES NOT EXIST.")

if __name__ == "__main__":
    check_table()
