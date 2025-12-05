from sqlalchemy import create_engine, inspect
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inspect_types():
    logger.info(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    for table in ["TEMP_ebay_orders", "ebay_orders"]:
        if inspector.has_table(table):
            print(f"\nTable: {table}")
            columns = inspector.get_columns(table)
            for c in columns:
                print(f"  - {c['name']}: {c['type']}")
        else:
            print(f"\nTable {table} NOT FOUND")

if __name__ == "__main__":
    inspect_types()
