"""Add accounting tables for internal bookkeeping

Revision ID: accounting_20251118
Revises: tasks_and_notifications_20251118
Create Date: 2025-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import NUMERIC


# revision identifiers, used by Alembic.
revision: str = "accounting_20251118"
down_revision: Union[str, Sequence[str], None] = "tasks_and_notifications_20251118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expense categories
    op.create_table(
        "accounting_expense_category",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Seed base categories
    expense_table = sa.table(
        "accounting_expense_category",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("type", sa.Text()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        expense_table,
        [
            {"code": "COGS", "name": "Cost of goods sold", "type": "expense", "is_active": True, "sort_order": 10},
            {"code": "SHIPPING", "name": "Shipping costs", "type": "expense", "is_active": True, "sort_order": 20},
            {"code": "EBAY_FEES", "name": "eBay fees", "type": "expense", "is_active": True, "sort_order": 30},
            {"code": "SOFTWARE", "name": "Software & subscriptions", "type": "expense", "is_active": True, "sort_order": 40},
            {"code": "PAYROLL_WAGES", "name": "Payroll - wages", "type": "expense", "is_active": True, "sort_order": 50},
            {"code": "PAYROLL_TAX", "name": "Payroll - taxes", "type": "expense", "is_active": True, "sort_order": 60},
            {"code": "CASH_MISC", "name": "Misc cash expenses", "type": "expense", "is_active": True, "sort_order": 70},
        ],
    )

    # Bank statements
    op.create_table(
        "accounting_bank_statement",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bank_name", sa.Text(), nullable=False),
        sa.Column("account_last4", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("statement_period_start", sa.Date(), nullable=True),
        sa.Column("statement_period_end", sa.Date(), nullable=True),
        sa.Column("opening_balance", NUMERIC(14, 2), nullable=True),
        sa.Column("closing_balance", NUMERIC(14, 2), nullable=True),
        sa.Column("total_debit", NUMERIC(14, 2), nullable=True),
        sa.Column("total_credit", NUMERIC(14, 2), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "accounting_bank_statement_file",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bank_statement_id", sa.BigInteger(), sa.ForeignKey("accounting_bank_statement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("uploaded_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
    )

    op.create_table(
        "accounting_bank_row",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bank_statement_id", sa.BigInteger(), sa.ForeignKey("accounting_bank_statement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=True),
        sa.Column("operation_date", sa.Date(), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("description_clean", sa.Text(), nullable=True),
        sa.Column("amount", NUMERIC(14, 2), nullable=False),
        sa.Column("balance_after", NUMERIC(14, 2), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("parsed_status", sa.Text(), nullable=False, server_default="auto_parsed"),
        sa.Column("match_status", sa.Text(), nullable=False, server_default="unmatched"),
        sa.Column("expense_category_id", sa.BigInteger(), sa.ForeignKey("accounting_expense_category.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_accounting_bank_row_statement", "accounting_bank_row", ["bank_statement_id"])
    op.create_index("idx_accounting_bank_row_operation_date", "accounting_bank_row", ["operation_date"])

    # Cash expenses
    op.create_table(
        "accounting_cash_expense",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", NUMERIC(14, 2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("paid_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("counterparty", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expense_category_id", sa.BigInteger(), sa.ForeignKey("accounting_expense_category.id"), nullable=False),
        sa.Column("storage_id", sa.Text(), nullable=True),
        sa.Column("receipt_image_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
    )

    # Unified accounting transactions
    op.create_table(
        "accounting_transaction",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", NUMERIC(14, 2), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=True),
        sa.Column("account_id", sa.Text(), nullable=True),
        sa.Column("counterparty", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expense_category_id", sa.BigInteger(), sa.ForeignKey("accounting_expense_category.id"), nullable=True),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("storage_id", sa.Text(), nullable=True),
        sa.Column("linked_object_type", sa.Text(), nullable=True),
        sa.Column("linked_object_id", sa.Text(), nullable=True),
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_internal_transfer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_accounting_txn_date", "accounting_transaction", ["date"])
    op.create_index("idx_accounting_txn_category", "accounting_transaction", ["expense_category_id"])
    op.create_index("idx_accounting_txn_storage", "accounting_transaction", ["storage_id"])
    op.create_index("idx_accounting_txn_source_type", "accounting_transaction", ["source_type"])

    # Transaction change log
    op.create_table(
        "accounting_transaction_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("transaction_id", sa.BigInteger(), sa.ForeignKey("accounting_transaction.id", ondelete="CASCADE"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("changed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("accounting_transaction_log")
    op.drop_index("idx_accounting_txn_source_type", table_name="accounting_transaction")
    op.drop_index("idx_accounting_txn_storage", table_name="accounting_transaction")
    op.drop_index("idx_accounting_txn_category", table_name="accounting_transaction")
    op.drop_index("idx_accounting_txn_date", table_name="accounting_transaction")
    op.drop_table("accounting_transaction")

    op.drop_table("accounting_cash_expense")

    op.drop_index("idx_accounting_bank_row_operation_date", table_name="accounting_bank_row")
    op.drop_index("idx_accounting_bank_row_statement", table_name="accounting_bank_row")
    op.drop_table("accounting_bank_row")
    op.drop_table("accounting_bank_statement_file")
    op.drop_table("accounting_bank_statement")

    op.drop_table("accounting_expense_category")
