"""Add processing metadata columns to ebay_events

Revision ID: ebay_events_processing_20251121
Revises: ebay_events_20251119
Create Date: 2025-11-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect


revision: str = "ebay_events_processing_20251121"
down_revision: Union[str, Sequence[str], None] = "20251120_add_title_to_sku_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add processed_at + processing_error columns and supporting index.

    The columns are added idempotently so the migration can run safely in
    environments where the table was created manually.
    """

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "ebay_events" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("ebay_events")}

    if "processed_at" not in columns:
        op.add_column(
            "ebay_events",
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "processing_error" not in columns:
        op.add_column(
            "ebay_events",
            sa.Column("processing_error", JSONB, nullable=True),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("ebay_events")}
    if "idx_ebay_events_topic_processed" not in existing_indexes:
        op.create_index(
            "idx_ebay_events_topic_processed",
            "ebay_events",
            ["topic", "processed_at"],
        )


def downgrade() -> None:
    """Drop processing metadata columns and index (best-effort)."""

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "ebay_events" not in tables:
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("ebay_events")}
    if "idx_ebay_events_topic_processed" in existing_indexes:
        op.drop_index("idx_ebay_events_topic_processed", table_name="ebay_events")

    columns = {col["name"] for col in inspector.get_columns("ebay_events")}

    if "processing_error" in columns:
        op.drop_column("ebay_events", "processing_error")
    if "processed_at" in columns:
        op.drop_column("ebay_events", "processed_at")
