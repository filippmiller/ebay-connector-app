"""Add parsed_body JSONB column to ebay_messages

Revision ID: ebay_msg_parsed_20251119
Revises: tasks_and_notifications_20251118
Create Date: 2025-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "ebay_msg_parsed_20251119"
down_revision: Union[str, Sequence[str], None] = "tasks_and_notifications_20251118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add parsed_body JSONB column if it does not already exist."""
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "ebay_messages" not in tables:
        return

    existing_cols = {c["name"] for c in inspector.get_columns("ebay_messages")}
    if "parsed_body" in existing_cols:
        return

    op.add_column("ebay_messages", sa.Column("parsed_body", JSONB, nullable=True))


def downgrade() -> None:
    """Drop parsed_body column if it exists."""
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "ebay_messages" not in tables:
        return

    existing_cols = {c["name"] for c in inspector.get_columns("ebay_messages")}
    if "parsed_body" in existing_cols:
        op.drop_column("ebay_messages", "parsed_body")