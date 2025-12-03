"""Add accounting pipeline tables and columns

Revision ID: accounting_pipeline_20251203
Revises: add_inventory_offers_20251203
Create Date: 2025-12-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import NUMERIC


# revision identifiers, used by Alembic.
revision: str = "accounting_pipeline_20251203"
down_revision: Union[str, Sequence[str], None] = "add_inventory_offers_20251203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add file_hash to accounting_bank_statement
    op.add_column("accounting_bank_statement", sa.Column("file_hash", sa.Text(), nullable=True))
    op.create_index("idx_accounting_bank_statement_file_hash", "accounting_bank_statement", ["file_hash"])

    # 2. Add dedupe_key to accounting_bank_row
    op.add_column("accounting_bank_row", sa.Column("dedupe_key", sa.Text(), nullable=True))
    op.create_index("idx_accounting_bank_row_dedupe_key", "accounting_bank_row", ["dedupe_key"])

    # 3. Add bank_row_id to accounting_transaction
    op.add_column("accounting_transaction", sa.Column("bank_row_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_accounting_transaction_bank_row_id",
        "accounting_transaction",
        "accounting_bank_row",
        ["bank_row_id"],
        ["id"],
    )
    op.create_unique_constraint("uq_accounting_transaction_bank_row_id", "accounting_transaction", ["bank_row_id"])

    # 4. Create accounting_bank_rule table
    op.create_table(
        "accounting_bank_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("pattern_type", sa.Text(), nullable=False),
        sa.Column("pattern_value", sa.Text(), nullable=False),
        sa.Column("expense_category_id", sa.BigInteger(), sa.ForeignKey("accounting_expense_category.id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_accounting_bank_rule_active_priority", "accounting_bank_rule", ["is_active", "priority"])


def downgrade() -> None:
    op.drop_index("idx_accounting_bank_rule_active_priority", table_name="accounting_bank_rule")
    op.drop_table("accounting_bank_rule")

    op.drop_constraint("uq_accounting_transaction_bank_row_id", "accounting_transaction", type_="unique")
    op.drop_constraint("fk_accounting_transaction_bank_row_id", "accounting_transaction", type_="foreignkey")
    op.drop_column("accounting_transaction", "bank_row_id")

    op.drop_index("idx_accounting_bank_row_dedupe_key", table_name="accounting_bank_row")
    op.drop_column("accounting_bank_row", "dedupe_key")

    op.drop_index("idx_accounting_bank_statement_file_hash", table_name="accounting_bank_statement")
    op.drop_column("accounting_bank_statement", "file_hash")
