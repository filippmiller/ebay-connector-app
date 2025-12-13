"""Add Bank Statement v1.0 fields to accounting tables

Revision ID: bank_statement_v1_20251206
Revises: 20251206_120000_add_raw_openai_response
Create Date: 2025-12-06 14:30

This migration adds new fields to support the Bank Statement v1.0 JSON schema
and internal PDF parsing pipeline. All changes are additive (no breaking changes).

New fields in accounting_bank_row:
- bank_code: Short bank identifier (TD, BOA, CITI)
- bank_section: Section in statement (ELECTRONIC_DEPOSIT, CHECKS_PAID, etc.)
- bank_subtype: Transaction subtype (CCD DEPOSIT, ACH DEBIT, etc.)
- direction: CREDIT or DEBIT
- accounting_group: Business classification (INCOME, COGS, etc.)
- classification: Detailed classification code (INCOME_EBAY_PAYOUT, etc.)
- classification_status: Processing status (OK, UNKNOWN, ERROR)
- check_number: Check number if applicable
- raw_transaction_json: Raw JSON from Bank Statement v1.0

New fields in accounting_bank_statement:
- raw_json: Full Bank Statement v1.0 JSON
- statement_hash: Hash for idempotency
- source_type: Source of statement (JSON_UPLOAD, PDF_TD, CSV, XLSX, OPENAI)
- bank_code: Short bank identifier
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "bank_statement_v1_20251206"
down_revision: Union[str, Sequence[str], None] = "20251206_120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================================================
    # accounting_bank_statement — Add new columns
    # ========================================================================
    
    # raw_json: Full Bank Statement v1.0 JSON object
    op.add_column(
        "accounting_bank_statement",
        sa.Column("raw_json", JSONB, nullable=True)
    )
    
    # statement_hash: For idempotency checking (bank_code + account + period)
    op.add_column(
        "accounting_bank_statement",
        sa.Column("statement_hash", sa.Text(), nullable=True)
    )
    op.create_index(
        "idx_accounting_bank_statement_stmt_hash",
        "accounting_bank_statement",
        ["statement_hash"]
    )
    
    # source_type: How the statement was imported
    op.add_column(
        "accounting_bank_statement",
        sa.Column("source_type", sa.Text(), nullable=True, server_default="MANUAL")
    )
    
    # bank_code: Short bank identifier
    op.add_column(
        "accounting_bank_statement",
        sa.Column("bank_code", sa.Text(), nullable=True)
    )
    op.create_index(
        "idx_accounting_bank_statement_bank_code",
        "accounting_bank_statement",
        ["bank_code"]
    )
    
    # ========================================================================
    # accounting_bank_row — Add Bank Statement v1.0 classification fields
    # ========================================================================
    
    # bank_code: Short bank identifier (TD, BOA, CITI)
    op.add_column(
        "accounting_bank_row",
        sa.Column("bank_code", sa.Text(), nullable=True)
    )
    
    # bank_section: Section in statement (ELECTRONIC_DEPOSIT, etc.)
    op.add_column(
        "accounting_bank_row",
        sa.Column("bank_section", sa.Text(), nullable=True)
    )
    
    # bank_subtype: Transaction subtype (CCD DEPOSIT, ACH DEBIT, etc.)
    op.add_column(
        "accounting_bank_row",
        sa.Column("bank_subtype", sa.Text(), nullable=True)
    )
    
    # direction: CREDIT or DEBIT
    op.add_column(
        "accounting_bank_row",
        sa.Column("direction", sa.Text(), nullable=True)
    )
    
    # accounting_group: Business classification
    op.add_column(
        "accounting_bank_row",
        sa.Column("accounting_group", sa.Text(), nullable=True)
    )
    
    # classification: Detailed classification code
    op.add_column(
        "accounting_bank_row",
        sa.Column("classification", sa.Text(), nullable=True)
    )
    
    # classification_status: Processing status
    op.add_column(
        "accounting_bank_row",
        sa.Column("classification_status", sa.Text(), nullable=True, server_default="UNKNOWN")
    )
    
    # check_number: Check number if applicable
    op.add_column(
        "accounting_bank_row",
        sa.Column("check_number", sa.Text(), nullable=True)
    )
    
    # raw_transaction_json: Raw JSON from Bank Statement v1.0
    op.add_column(
        "accounting_bank_row",
        sa.Column("raw_transaction_json", JSONB, nullable=True)
    )
    
    # Add indexes for common query patterns
    op.create_index(
        "idx_accounting_bank_row_bank_code",
        "accounting_bank_row",
        ["bank_code"]
    )
    op.create_index(
        "idx_accounting_bank_row_bank_section",
        "accounting_bank_row",
        ["bank_section"]
    )
    op.create_index(
        "idx_accounting_bank_row_direction",
        "accounting_bank_row",
        ["direction"]
    )
    op.create_index(
        "idx_accounting_bank_row_accounting_group",
        "accounting_bank_row",
        ["accounting_group"]
    )
    op.create_index(
        "idx_accounting_bank_row_classification",
        "accounting_bank_row",
        ["classification"]
    )
    op.create_index(
        "idx_accounting_bank_row_classification_status",
        "accounting_bank_row",
        ["classification_status"]
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("idx_accounting_bank_row_classification_status", table_name="accounting_bank_row")
    op.drop_index("idx_accounting_bank_row_classification", table_name="accounting_bank_row")
    op.drop_index("idx_accounting_bank_row_accounting_group", table_name="accounting_bank_row")
    op.drop_index("idx_accounting_bank_row_direction", table_name="accounting_bank_row")
    op.drop_index("idx_accounting_bank_row_bank_section", table_name="accounting_bank_row")
    op.drop_index("idx_accounting_bank_row_bank_code", table_name="accounting_bank_row")
    
    # Drop accounting_bank_row columns
    op.drop_column("accounting_bank_row", "raw_transaction_json")
    op.drop_column("accounting_bank_row", "check_number")
    op.drop_column("accounting_bank_row", "classification_status")
    op.drop_column("accounting_bank_row", "classification")
    op.drop_column("accounting_bank_row", "accounting_group")
    op.drop_column("accounting_bank_row", "direction")
    op.drop_column("accounting_bank_row", "bank_subtype")
    op.drop_column("accounting_bank_row", "bank_section")
    op.drop_column("accounting_bank_row", "bank_code")
    
    # Drop accounting_bank_statement indexes and columns
    op.drop_index("idx_accounting_bank_statement_bank_code", table_name="accounting_bank_statement")
    op.drop_column("accounting_bank_statement", "bank_code")
    op.drop_column("accounting_bank_statement", "source_type")
    op.drop_index("idx_accounting_bank_statement_stmt_hash", table_name="accounting_bank_statement")
    op.drop_column("accounting_bank_statement", "statement_hash")
    op.drop_column("accounting_bank_statement", "raw_json")
