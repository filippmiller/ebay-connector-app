from sqlalchemy import create_engine, text, inspect
from app.config import settings
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_data():
    logger.info(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # Inspect TEMP table
        temp_cols = [c['name'] for c in inspector.get_columns("TEMP_ebay_orders")]
        logger.info(f"TEMP_ebay_orders columns: {temp_cols}")
        
        # Inspect target table
        target_cols = [c['name'] for c in inspector.get_columns("ebay_orders")]
        logger.info(f"ebay_orders columns: {target_cols}")

        # Check count in temp table
        result = conn.execute(text("SELECT COUNT(*) FROM \"TEMP_ebay_orders\""))
        temp_count = result.scalar()
        logger.info(f"Found {temp_count} rows in TEMP_ebay_orders")
        
        if temp_count == 0:
            logger.info("No data to migrate.")
            return

        # Perform migration
        # We map columns explicitly to be safe
        query = text("""
            INSERT INTO ebay_orders (
                order_id, user_id, ebay_account_id, ebay_user_id,
                creation_date, last_modified_date,
                order_payment_status, order_fulfillment_status,
                buyer_username, buyer_email,
                tracking_number, ship_to_name, ship_to_city, ship_to_state,
                ship_to_postal_code, ship_to_country_code,
                raw_payload,
                created_at, updated_at
            )
            SELECT 
                order_id, user_id, ebay_account_id, ebay_user_id,
                creation_date, last_modified_date,
                order_payment_status, order_fulfillment_status,
                buyer_username, buyer_email,
                tracking_number, ship_to_name, ship_to_city, ship_to_state,
                ship_to_postal_code, ship_to_country_code,
                raw_payload,
                NOW(), NOW()
            FROM "TEMP_ebay_orders"
            ON CONFLICT (order_id, user_id) DO NOTHING
        """)
        
        result = conn.execute(query)
        conn.commit()
        logger.info(f"Migrated {result.rowcount} rows to ebay_orders")
        
        # Verify count
        result = conn.execute(text("SELECT COUNT(*) FROM ebay_orders"))
        new_count = result.scalar()
        logger.info(f"Total rows in ebay_orders: {new_count}")

if __name__ == "__main__":
    migrate_data()
