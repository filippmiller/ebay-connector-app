"""Add ebay_inquiries table for Post-Order inquiries

Revision ID: ebay_inquiries_20251124
Revises: ebay_messages_normalization_20251124
Create Date: 2025-11-24

This migration introduces the ebay_inquiries table used to store normalized
Post-Order inquiry records (the pre-case buyer disputes) with raw JSON payloads
for auditing. The DDL follows the same style as other eBay data tables and is
safe to apply once on top of existing schemas.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ebay_inquiries_20251124"
down_revision: Union[str, Sequence[str], None] = "ebay_messages_normalization_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ebay_inquiries"


def upgrade() -> None:
    """Create the ebay_inquiries table."""

    op.create_table(
        TABLE_NAME,
        sa.Column("inquiry_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("ebay_account_id", sa.String(length=36), nullable=True),
        sa.Column("ebay_user_id", sa.String(length=64), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("item_id", sa.String(length=100), nullable=True),
        sa.Column("transaction_id", sa.String(length=100), nullable=True),
        sa.Column("buyer_username", sa.Text(), nullable=True),
        sa.Column("seller_username", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("issue_type", sa.String(length=50), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_update_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_amount_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("claim_amount_currency", sa.String(length=10), nullable=True),
        sa.Column("desired_outcome", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("inquiry_id", "user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        # ebay_account_id is a loose FK; keep it nullable to allow legacy rows
        # or data created before ebay_accounts are fully populated.
        sa.ForeignKeyConstraint(["ebay_account_id"], ["ebay_accounts.id"], use_alter=True, name="fk_ebay_inquiries_account"),
    )

    op.create_index("idx_ebay_inquiries_user_id", TABLE_NAME, ["user_id"])
    op.create_index("idx_ebay_inquiries_order_id", TABLE_NAME, ["order_id"])
    op.create_index("idx_ebay_inquiries_buyer_username", TABLE_NAME, ["buyer_username"])
    op.create_index("idx_ebay_inquiries_opened_at", TABLE_NAME, ["opened_at"])
    op.create_index(
        "idx_ebay_inquiries_account_inquiry",
        TABLE_NAME,
        ["ebay_account_id", "inquiry_id"],
    )


def downgrade() -> None:
    """Drop ebay_inquiries table and its indexes."""

    op.drop_index("idx_ebay_inquiries_account_inquiry", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_inquiries_opened_at", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_inquiries_buyer_username", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_inquiries_order_id", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_inquiries_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
