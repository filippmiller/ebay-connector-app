from sqlalchemy import create_engine, text
from app.config import settings

def check_orders_count():
    print(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        try:
            result = conn.execute(text('SELECT COUNT(*) FROM ebay_orders'))
            count = result.scalar()
            print(f"ebay_orders count: {count}")
        except Exception as e:
            print(f"Error checking count: {e}")

if __name__ == "__main__":
    check_orders_count()
