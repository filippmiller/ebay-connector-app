"""Add ebay_snipes table for internal eBay auction sniper

Revision ID: ebay_snipes_20251124
Revises: ebay_inquiries_20251124
Create Date: 2025-11-24

This migration introduces the ebay_snipes table used by the internal
"Sniper/Bidnapper" module to store scheduled last-second bids for eBay
auctions.

NOTE: Do NOT run this migration until DATABASE_URL for the production
Supabase Postgres is valid and Alembic can connect without tenant/user
errors.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ebay_snipes_20251124"
down_revision: Union[str, Sequence[str], None] = "ebay_inquiries_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ebay_snipes"


def upgrade() -> None:
    """Create the ebay_snipes table used by the Sniper module."""

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("ebay_account_id", sa.String(length=36), nullable=True),
        sa.Column("item_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_bid_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="USD"),
        sa.Column("seconds_before_end", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("current_bid_at_creation", sa.Numeric(14, 2), nullable=True),
        sa.Column("result_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("contingency_group_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ebay_snipes_user"),
        sa.ForeignKeyConstraint(
            ["ebay_account_id"],
            ["ebay_accounts.id"],
            name="fk_ebay_snipes_account",
            ondelete="CASCADE",
            use_alter=True,
        ),
    )

    op.create_index("idx_ebay_snipes_user_id", TABLE_NAME, ["user_id"])
    op.create_index("idx_ebay_snipes_account_id", TABLE_NAME, ["ebay_account_id"])
    op.create_index("idx_ebay_snipes_status", TABLE_NAME, ["status"])
    op.create_index("idx_ebay_snipes_end_time", TABLE_NAME, ["end_time"])


def downgrade() -> None:
    """Drop ebay_snipes table and its indexes (best-effort)."""

    op.drop_index("idx_ebay_snipes_end_time", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_snipes_status", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_snipes_account_id", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_snipes_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)