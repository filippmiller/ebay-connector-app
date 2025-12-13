from sqlalchemy import create_engine, text
from app.config import settings

def check_temp_count():
    print(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        try:
            result = conn.execute(text('SELECT COUNT(*) FROM "TEMP_ebay_orders"'))
            temp_count = result.scalar()
            print(f"TEMP_ebay_orders count: {temp_count}")
        except Exception as e:
            print(f"Error checking count: {e}")

if __name__ == "__main__":
    check_temp_count()
