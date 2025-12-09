"""Add tables for eBay test-listing config and logs

Revision ID: 20251209_add_ebay_listing_test_logs
Revises: 20251209_add_inventory_mv_worker_settings
Create Date: 2025-12-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20251209_add_ebay_listing_test_logs"
down_revision: Union[str, Sequence[str], None] = "20251209_add_inventory_mv_worker_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Config table: single-row toggle and basic settings for the test-listing UI.
    op.create_table(
        "ebay_listing_test_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("debug_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("test_inventory_status", sa.String(length=50), nullable=True),
        sa.Column("max_items_per_run", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Logs table: per-run trace snapshot for the test-listing worker.
    op.create_table(
        "ebay_listing_test_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("inventory_id", sa.Integer(), nullable=True),
        sa.Column("parts_detail_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("account_label", sa.String(length=200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventory.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parts_detail_id"], ["parts_detail.id"], ondelete="SET NULL"),
    )

    op.create_index(
        "idx_ebay_listing_test_logs_created_at",
        "ebay_listing_test_logs",
        ["created_at"],
    )
    op.create_index(
        "idx_ebay_listing_test_logs_status",
        "ebay_listing_test_logs",
        ["status"],
    )
    op.create_index(
        "ix_ebay_listing_test_logs_inventory_id",
        "ebay_listing_test_logs",
        ["inventory_id"],
    )
    op.create_index(
        "ix_ebay_listing_test_logs_parts_detail_id",
        "ebay_listing_test_logs",
        ["parts_detail_id"],
    )
    op.create_index(
        "ix_ebay_listing_test_logs_sku",
        "ebay_listing_test_logs",
        ["sku"],
    )


def downgrade() -> None:
    op.drop_index("ix_ebay_listing_test_logs_sku", table_name="ebay_listing_test_logs")
    op.drop_index("ix_ebay_listing_test_logs_parts_detail_id", table_name="ebay_listing_test_logs")
    op.drop_index("ix_ebay_listing_test_logs_inventory_id", table_name="ebay_listing_test_logs")
    op.drop_index("idx_ebay_listing_test_logs_status", table_name="ebay_listing_test_logs")
    op.drop_index("idx_ebay_listing_test_logs_created_at", table_name="ebay_listing_test_logs")
    op.drop_table("ebay_listing_test_logs")
    op.drop_table("ebay_listing_test_config")
