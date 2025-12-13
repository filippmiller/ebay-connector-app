"""Add source column to ebay_connect_logs

Revision ID: add_source_to_ebay_connect_logs_20251201
Revises: ebay_connect_logs_001
Create Date: 2025-12-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "add_source_to_ebay_connect_logs_20251201"
down_revision = "ebay_connect_logs_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a nullable source column and index to ebay_connect_logs.

    The source column carries a short label such as "debug", "scheduled",
    or "admin" so the admin UI can distinguish manual vs worker calls in the
    unified Token Refresh Terminal.
    """
    conn = op.get_bind()
    inspector = inspect(conn)

    columns = {c["name"] for c in inspector.get_columns("ebay_connect_logs")}
    if "source" not in columns:
        op.add_column(
            "ebay_connect_logs",
            sa.Column("source", sa.String(length=32), nullable=True),
        )

    indexes = {ix["name"] for ix in inspector.get_indexes("ebay_connect_logs")}
    if "idx_ebay_connect_logs_source" not in indexes:
        op.create_index(
            "idx_ebay_connect_logs_source",
            "ebay_connect_logs",
            ["source"],
        )


def downgrade() -> None:
    """Drop source index/column from ebay_connect_logs (if present)."""
    conn = op.get_bind()
    inspector = inspect(conn)

    indexes = {ix["name"] for ix in inspector.get_indexes("ebay_connect_logs")}
    if "idx_ebay_connect_logs_source" in indexes:
        op.drop_index("idx_ebay_connect_logs_source", table_name="ebay_connect_logs")

    columns = {c["name"] for c in inspector.get_columns("ebay_connect_logs")}
    if "source" in columns:
        op.drop_column("ebay_connect_logs", "source")
