import os
import uuid
from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

print("Connecting to database...")

with engine.begin() as conn:
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("ebay_messages")}
    print(f"Existing columns in ebay_messages: {sorted(cols)}")

    # 1) Add id column if missing
    if "id" not in cols:
        print("Adding id column (varchar(36)) to ebay_messages...")
        conn.execute(text("ALTER TABLE ebay_messages ADD COLUMN id varchar(36)"))

        print("Backfilling id values for existing rows...")
        rows = conn.execute(
            text(
                "SELECT message_id, user_id, ebay_account_id "
                "FROM ebay_messages "
                "WHERE id IS NULL"
            )
        ).fetchall()
        print(f"Found {len(rows)} rows needing id backfill")
        for r in rows:
            conn.execute(
                text(
                    "UPDATE ebay_messages "
                    "SET id = :id "
                    "WHERE message_id = :mid AND user_id = :uid AND ebay_account_id = :aid"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "mid": r["message_id"],
                    "uid": r["user_id"],
                    "aid": r["ebay_account_id"],
                },
            )

        print("Setting id column to NOT NULL...")
        conn.execute(text("ALTER TABLE ebay_messages ALTER COLUMN id SET NOT NULL"))
    else:
        print("Column id already exists; skipping add/backfill")

    # 2) Drop old composite PK if present and add new PK on id
    print("Dropping old primary key constraint if it exists...")
    conn.execute(text("ALTER TABLE ebay_messages DROP CONSTRAINT IF EXISTS ebay_messages_pkey"))

    print("Adding primary key on id...")
    conn.execute(text("ALTER TABLE ebay_messages ADD PRIMARY KEY (id)"))

    # 3) Ensure unique index on (ebay_account_id, user_id, message_id)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("ebay_messages")}
    print(f"Existing indexes on ebay_messages: {sorted(existing_indexes)}")
    if "uq_ebay_messages_account_user_msgid" not in existing_indexes:
        print("Creating unique index uq_ebay_messages_account_user_msgid on (ebay_account_id, user_id, message_id)...")
        conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_ebay_messages_account_user_msgid "
                "ON ebay_messages (ebay_account_id, user_id, message_id)"
            )
        )
    else:
        print("Unique index uq_ebay_messages_account_user_msgid already exists; skipping")

print("ebay_messages schema updated successfully.")
