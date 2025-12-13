"""Add ebay_snipe_logs table and has_bid flag for sniper bids

Revision ID: ebay_snipe_logs_20251125
Revises: parts_detail_20251125
Create Date: 2025-11-25

This migration introduces a dedicated audit log table for sniper executions
(ebay_snipe_logs) and a lightweight has_bid flag on ebay_snipes to indicate
that at least one bid attempt was made for the snipe.

The log table is intentionally generic so it can store both stub
implementations and the future real PlaceOffer/Browse API responses.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ebay_snipe_logs_20251125"
down_revision: Union[str, Sequence[str], None] = "parts_detail_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SNIPES_TABLE = "ebay_snipes"
LOGS_TABLE = "ebay_snipe_logs"


def upgrade() -> None:
    """Add has_bid to ebay_snipes and create ebay_snipe_logs table."""

    # 1) Lightweight has_bid flag on the main snipes table.
    op.add_column(
        SNIPES_TABLE,
        sa.Column("has_bid", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Drop server_default after initial creation; ORM-level defaults will be used
    # for new rows.
    op.alter_column(SNIPES_TABLE, "has_bid", server_default=None)

    # 2) Dedicated log table for all bid-related events.
    op.create_table(
        LOGS_TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "snipe_id",
            sa.String(length=36),
            sa.ForeignKey("ebay_snipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("ebay_bid_id", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        # Full raw payload from eBay or a structured summary (JSON-as-text).
        sa.Column("payload", sa.Text(), nullable=True),
        # Short human-readable message suitable for display in the UI.
        sa.Column("message", sa.Text(), nullable=True),
    )

    op.create_index(
        "idx_ebay_snipe_logs_snipe_id_created_at",
        LOGS_TABLE,
        ["snipe_id", "created_at"],
    )


def downgrade() -> None:
    """Drop ebay_snipe_logs and has_bid flag (best-effort)."""

    op.drop_index("idx_ebay_snipe_logs_snipe_id_created_at", table_name=LOGS_TABLE)
    op.drop_table(LOGS_TABLE)
    op.drop_column(SNIPES_TABLE, "has_bid")
