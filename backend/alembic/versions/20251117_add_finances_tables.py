"""Add tables for eBay finances transactions and fees

Revision ID: ebay_finances_20251117
Revises: ebay_workers_20251115
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Numeric, CHAR

# revision identifiers, used by Alembic.
revision = "ebay_finances_20251117"
down_revision = "ebay_workers_20251115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ebay_finances_transactions and ebay_finances_fees tables.

    These tables store normalized data from the Sell Finances getTransactions
    API, keyed by internal ebay_account_id and transaction_id.
    """

    op.create_table(
        "ebay_finances_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ebay_account_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("ebay_user_id", sa.String(length=64), nullable=False),
        sa.Column("transaction_id", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("transaction_status", sa.String(length=50), nullable=True),
        sa.Column("booking_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transaction_amount_value", Numeric(18, 4), nullable=True),
        sa.Column("transaction_amount_currency", CHAR(3), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("order_line_item_id", sa.String(length=100), nullable=True),
        sa.Column("payout_id", sa.String(length=100), nullable=True),
        sa.Column("seller_reference", sa.String(length=100), nullable=True),
        sa.Column("transaction_memo", sa.Text(), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Unique transaction per account
    op.create_index(
        "uq_finances_txn_account_txnid",
        "ebay_finances_transactions",
        ["ebay_account_id", "transaction_id"],
        unique=True,
    )

    # Helpful secondary indexes
    op.create_index(
        "idx_finances_txn_account_booking_date",
        "ebay_finances_transactions",
        ["ebay_account_id", "booking_date"],
    )
    op.create_index(
        "idx_finances_txn_order_id",
        "ebay_finances_transactions",
        ["order_id"],
    )
    op.create_index(
        "idx_finances_txn_order_line_item_id",
        "ebay_finances_transactions",
        ["order_line_item_id"],
    )
    op.create_index(
        "idx_finances_txn_type",
        "ebay_finances_transactions",
        ["transaction_type"],
    )

    # Child table: individual fee lines for a transaction
    op.create_table(
        "ebay_finances_fees",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ebay_account_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=100), nullable=False),
        sa.Column("fee_type", sa.String(length=100), nullable=True),
        sa.Column("amount_value", Numeric(18, 4), nullable=True),
        sa.Column("amount_currency", CHAR(3), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "idx_finances_fees_account_txnid",
        "ebay_finances_fees",
        ["ebay_account_id", "transaction_id"],
    )
    op.create_index(
        "idx_finances_fees_type",
        "ebay_finances_fees",
        ["fee_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_finances_fees_type", table_name="ebay_finances_fees")
    op.drop_index("idx_finances_fees_account_txnid", table_name="ebay_finances_fees")
    op.drop_table("ebay_finances_fees")

    op.drop_index("idx_finances_txn_type", table_name="ebay_finances_transactions")
    op.drop_index("idx_finances_txn_order_line_item_id", table_name="ebay_finances_transactions")
    op.drop_index("idx_finances_txn_order_id", table_name="ebay_finances_transactions")
    op.drop_index("idx_finances_txn_account_booking_date", table_name="ebay_finances_transactions")
    op.drop_index("uq_finances_txn_account_txnid", table_name="ebay_finances_transactions")
    op.drop_table("ebay_finances_transactions")
