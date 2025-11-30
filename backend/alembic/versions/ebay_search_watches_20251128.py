"""Create ebay_search_watches table for eBay auto-search rules

Revision ID: ebay_search_watches_20251128
Revises: db_migration_workers_notifications_20251126
Create Date: 2025-11-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ebay_search_watches_20251128"
down_revision: Union[str, Sequence[str], None] = "db_migration_workers_notifications_20251126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ebay_search_watches"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=False),
        sa.Column("max_total_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("category_hint", sa.String(length=50), nullable=True),
        sa.Column("exclude_keywords", sa.JSON(), nullable=True),
        sa.Column("marketplace_id", sa.String(length=20), nullable=False, server_default="EBAY_US"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("check_interval_sec", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_item_ids", sa.JSON(), nullable=True),
        sa.Column("notification_mode", sa.String(length=20), nullable=False, server_default="task"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "idx_ebay_search_watches_user_id",
        TABLE_NAME,
        ["user_id"],
    )
    op.create_index(
        "idx_ebay_search_watches_enabled",
        TABLE_NAME,
        ["enabled"],
    )
    op.create_index(
        "idx_ebay_search_watches_last_checked",
        TABLE_NAME,
        ["last_checked_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ebay_search_watches_last_checked", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_search_watches_enabled", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_search_watches_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
