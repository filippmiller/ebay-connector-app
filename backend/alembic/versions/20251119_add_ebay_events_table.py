"""Create unified ebay_events table for eBay Notifications Center

Revision ID: ebay_events_20251119
Revises: ebay_msg_parsed_20251119
Create Date: 2025-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import inspect, text


revision: str = "ebay_events_20251119"
down_revision: Union[str, Sequence[str], None] = "ebay_msg_parsed_20251119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ebay_events table and required indexes (idempotent)."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    # Best-effort enable pgcrypto so gen_random_uuid() is available on Postgres.
    try:
        op.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    except Exception:
        # Extension creation may fail on limited environments; ignore best-effort error.
        pass

    if "ebay_events" not in existing_tables:
        op.create_table(
            "ebay_events",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("channel", sa.Text(), nullable=False),
            sa.Column("topic", sa.Text(), nullable=True),
            sa.Column("entity_type", sa.Text(), nullable=True),
            sa.Column("entity_id", sa.Text(), nullable=True),
            sa.Column("ebay_account", sa.Text(), nullable=True),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("publish_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'RECEIVED'"),
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "headers",
                JSONB,
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("signature_valid", sa.Boolean(), nullable=True),
            sa.Column("signature_kid", sa.Text(), nullable=True),
            sa.Column("payload", JSONB, nullable=False),
        )

        existing_tables.append("ebay_events")

    # Ensure indexes exist even if table was created outside Alembic.
    existing_indexes_by_table = {
        t: {idx["name"] for idx in inspector.get_indexes(t)} for t in existing_tables
    }
    existing_indexes = existing_indexes_by_table.get("ebay_events", set())

    if "idx_ebay_events_topic_time" not in existing_indexes:
        op.create_index(
            "idx_ebay_events_topic_time",
            "ebay_events",
            ["topic", "event_time"],
        )

    if "idx_ebay_events_entity" not in existing_indexes:
        op.create_index(
            "idx_ebay_events_entity",
            "ebay_events",
            ["entity_type", "entity_id"],
        )

    if "idx_ebay_events_account_time" not in existing_indexes:
        op.create_index(
            "idx_ebay_events_account_time",
            "ebay_events",
            ["ebay_account", "event_time"],
        )


def downgrade() -> None:
    """Drop ebay_events table and its indexes (best-effort)."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "ebay_events" in existing_tables:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("ebay_events")}

        if "idx_ebay_events_account_time" in existing_indexes:
            op.drop_index("idx_ebay_events_account_time", table_name="ebay_events")
        if "idx_ebay_events_entity" in existing_indexes:
            op.drop_index("idx_ebay_events_entity", table_name="ebay_events")
        if "idx_ebay_events_topic_time" in existing_indexes:
            op.drop_index("idx_ebay_events_topic_time", table_name="ebay_events")

        op.drop_table("ebay_events")
