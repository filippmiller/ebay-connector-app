from sqlalchemy import create_engine, text
from app.config import settings

def check_line_items():
    print(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM order_line_items"))
        count = result.scalar()
        print(f"Total rows in order_line_items: {count}")

if __name__ == "__main__":
    check_line_items()
