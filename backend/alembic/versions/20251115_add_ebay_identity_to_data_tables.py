"""Add ebay_account_id and ebay_user_id to eBay data tables

Revision ID: ebay_identity_20251115
Revises: ebay_workers_20251115
Create Date: 2025-11-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "ebay_identity_20251115"
down_revision: Union[str, Sequence[str], None] = "ebay_workers_20251115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TARGET_TABLES = [
    "ebay_orders",
    "order_line_items",
    "ebay_transactions",
    "transactions",
    "ebay_offers",
    "ebay_disputes",
    "ebay_cases",
    "ebay_messages",
    "inventory",
    "purchases",
    "purchase_line_items",
    "fees",
    "payouts",
    "payout_items",
]


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    """Add a column to table if it does not already exist.

    This migration is written to be idempotent across environments that may
    already have some of these columns from earlier experiments.
    """

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    if table not in existing_tables:
        return

    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if column.name in existing_cols:
        return

    op.add_column(table, column)


def upgrade() -> None:
    # For each target table, ensure ebay_account_id and ebay_user_id columns exist.
    for table in TARGET_TABLES:
        _add_column_if_missing(
            table,
            sa.Column("ebay_account_id", sa.String(length=36), nullable=True),
        )
        _add_column_if_missing(
            table,
            sa.Column("ebay_user_id", sa.String(length=100), nullable=True),
        )


def downgrade() -> None:
    # Best-effort downgrade: drop the columns if they exist.
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    for table in TARGET_TABLES:
        if table not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if "ebay_user_id" in existing_cols:
            op.drop_column(table, "ebay_user_id")
        if "ebay_account_id" in existing_cols:
            op.drop_column(table, "ebay_account_id")
