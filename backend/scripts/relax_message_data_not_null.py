import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

print("Connecting to database...")

with engine.begin() as conn:
    print("Dropping NOT NULL constraint from ebay_messages.message_data (if any)...")
    conn.execute(text("ALTER TABLE ebay_messages ALTER COLUMN message_data DROP NOT NULL"))

print("Done: ebay_messages.message_data is now nullable.")
