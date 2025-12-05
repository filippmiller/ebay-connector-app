from sqlalchemy import create_engine, text
from app.config import settings

def check_index():
    print(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM pg_indexes WHERE indexname = 'idx_ebay_orders_creation_date'"))
        rows = result.fetchall()
        if rows:
            print(f"Found index 'idx_ebay_orders_creation_date': {rows}")
        else:
            print("Index 'idx_ebay_orders_creation_date' NOT FOUND.")

if __name__ == "__main__":
    check_index()
