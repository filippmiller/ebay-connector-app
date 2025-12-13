"""Add ebay_returns table for Post-Order returns

Revision ID: ebay_returns_20251201
Revises: ebay_inquiries_20251124
Create Date: 2025-12-01

This migration introduces the ebay_returns table used to store normalized
Post-Order return records with raw JSON payloads for auditing. The DDL follows
existing eBay data tables and is safe to apply once on top of existing schemas.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ebay_returns_20251201"
down_revision: Union[str, Sequence[str], None] = "ebay_inquiries_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ebay_returns"


def upgrade() -> None:
    """Create the ebay_returns table."""

    op.create_table(
        TABLE_NAME,
        sa.Column("return_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("ebay_account_id", sa.String(length=36), nullable=True),
        sa.Column("ebay_user_id", sa.String(length=64), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("item_id", sa.String(length=100), nullable=True),
        sa.Column("transaction_id", sa.String(length=100), nullable=True),
        sa.Column("return_state", sa.String(length=50), nullable=True),
        sa.Column("return_type", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("buyer_username", sa.Text(), nullable=True),
        sa.Column("seller_username", sa.Text(), nullable=True),
        sa.Column("total_amount_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_amount_currency", sa.String(length=10), nullable=True),
        sa.Column("creation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("return_id", "user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint([
            "ebay_account_id",
        ], ["ebay_accounts.id"], use_alter=True, name="fk_ebay_returns_account"),
    )

    op.create_index("idx_ebay_returns_user_id", TABLE_NAME, ["user_id"])
    op.create_index(
        "idx_ebay_returns_account_return",
        TABLE_NAME,
        ["ebay_account_id", "return_id"],
        unique=True,
    )
    op.create_index(
        "idx_ebay_returns_state_last_modified",
        TABLE_NAME,
        ["ebay_account_id", "return_state", "last_modified_date"],
    )
    op.create_index(
        "idx_ebay_returns_creation_date",
        TABLE_NAME,
        ["ebay_account_id", "creation_date"],
    )


def downgrade() -> None:
    """Drop ebay_returns table and its indexes."""

    op.drop_index("idx_ebay_returns_creation_date", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_returns_state_last_modified", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_returns_account_return", table_name=TABLE_NAME)
    op.drop_index("idx_ebay_returns_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
