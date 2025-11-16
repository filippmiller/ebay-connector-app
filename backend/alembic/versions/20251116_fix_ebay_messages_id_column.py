"""Fix ebay_messages schema to match SQLAlchemy model

Revision ID: fix_ebay_messages_id_column_001
Revises: add_active_inventory_snapshot_001
Create Date: 2025-11-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_ebay_messages_id_column_001'
down_revision = 'add_active_inventory_snapshot_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add id primary key and unique index on (ebay_account_id, user_id, message_id).

    The original ebay_messages table was created without an id column and used a
    composite primary key on (message_id, user_id). The SQLAlchemy model now
    expects an "id" column as the primary key. This migration adds that column
    and adjusts constraints accordingly.
    """
    # Add id column if it doesn't exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("ebay_messages")]

    if "id" not in columns:
        op.add_column("ebay_messages", sa.Column("id", sa.String(length=36), nullable=False))

    # Drop old composite primary key if present
    # The original migration used PrimaryKeyConstraint('message_id', 'user_id').
    # By default, Postgres will name this constraint "ebay_messages_pkey".
    op.execute("ALTER TABLE ebay_messages DROP CONSTRAINT IF EXISTS ebay_messages_pkey")

    # Create new primary key on id
    op.execute("ALTER TABLE ebay_messages ADD PRIMARY KEY (id)")

    # Create a unique index on (ebay_account_id, user_id, message_id) to prevent duplicates
    # Only create if it does not already exist.
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("ebay_messages")}
    if "uq_ebay_messages_account_user_msgid" not in existing_indexes:
        op.create_unique_constraint(
            "uq_ebay_messages_account_user_msgid",
            "ebay_messages",
            ["ebay_account_id", "user_id", "message_id"],
        )


def downgrade() -> None:
    """Revert to the old composite primary key and remove id/unique constraint.

    NOTE: This is primarily for development; downgrading in production should be
    considered carefully if data already relies on the id primary key.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Drop unique constraint if it exists
    existing_constraints = {uc["name"] for uc in inspector.get_unique_constraints("ebay_messages")}
    if "uq_ebay_messages_account_user_msgid" in existing_constraints:
        op.drop_constraint("uq_ebay_messages_account_user_msgid", "ebay_messages", type_="unique")

    # Drop primary key on id
    op.execute("ALTER TABLE ebay_messages DROP CONSTRAINT IF EXISTS ebay_messages_pkey")

    # Restore composite primary key on (message_id, user_id)
    op.execute("ALTER TABLE ebay_messages ADD PRIMARY KEY (message_id, user_id)")

    # Drop id column if it exists
    columns = [c["name"] for c in inspector.get_columns("ebay_messages")]
    if "id" in columns:
        op.drop_column("ebay_messages", "id")
