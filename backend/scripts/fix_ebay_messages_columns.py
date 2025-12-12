import os
from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

print("Connecting to database...")

with engine.begin() as conn:
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("ebay_messages")}
    print(f"Existing columns in ebay_messages: {sorted(cols)}")

    def add_column_if_missing(name: str, ddl: str) -> None:
        if name in cols:
            print(f"Column {name} already exists; skipping")
        else:
            print(f"Adding column {name} with DDL: {ddl}")
            conn.execute(text(f"ALTER TABLE ebay_messages ADD COLUMN {ddl}"))

    # Columns expected by app.models_sqlalchemy.models.Message
    add_column_if_missing("house_name", "house_name text")
    add_column_if_missing("sender_username", "sender_username varchar(100)")
    add_column_if_missing("recipient_username", "recipient_username varchar(100)")
    add_column_if_missing("body", "body text")
    add_column_if_missing("message_type", "message_type varchar(50)")
    add_column_if_missing("is_flagged", "is_flagged boolean DEFAULT false")
    add_column_if_missing("is_archived", "is_archived boolean DEFAULT false")
    add_column_if_missing("direction", "direction varchar(20)")
    add_column_if_missing("read_date", "read_date timestamptz")
    add_column_if_missing("listing_id", "listing_id varchar(100)")
    add_column_if_missing("raw_data", "raw_data text")

print("ebay_messages columns updated successfully.")
