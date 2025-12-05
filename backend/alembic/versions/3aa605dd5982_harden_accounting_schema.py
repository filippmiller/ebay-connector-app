"""harden_accounting_schema

Revision ID: 3aa605dd5982
Revises: 4de540d858ec
Create Date: 2025-12-05 13:42:37.031028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3aa605dd5982'
down_revision: Union[str, Sequence[str], None] = '4de540d858ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # 1. Create bank_transaction_category_internal
    op.create_table(
        'bank_transaction_category_internal',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.ForeignKeyConstraint(['parent_id'], ['bank_transaction_category_internal.id'], )
    )

    # 2. Create bank_statement_import_run
    op.create_table(
        'bank_statement_import_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bank_statement_id', sa.BigInteger(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='RUNNING', nullable=False),
        sa.Column('openai_model', sa.String(length=50), nullable=True),
        sa.Column('openai_request_id', sa.Text(), nullable=True),
        sa.Column('transactions_total', sa.Integer(), server_default='0', nullable=True),
        sa.Column('transactions_inserted', sa.Integer(), server_default='0', nullable=True),
        sa.Column('duplicates_skipped', sa.Integer(), server_default='0', nullable=True),
        sa.Column('balance_difference', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_statement_id'], ['accounting_bank_statement.id'], ondelete='CASCADE')
    )
    op.create_index('ix_bank_statement_import_run_bank_statement_id', 'bank_statement_import_run', ['bank_statement_id'], unique=False)

    # 3. Add columns to accounting_bank_statement
    op.add_column('accounting_bank_statement', sa.Column('supabase_bucket', sa.Text(), nullable=True))
    op.add_column('accounting_bank_statement', sa.Column('supabase_path', sa.Text(), nullable=True))
    op.add_column('accounting_bank_statement', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('accounting_bank_statement', sa.Column('raw_header_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 4. Add columns to accounting_bank_row
    op.add_column('accounting_bank_row', sa.Column('llm_category', sa.Text(), server_default='unknown', nullable=False))
    op.add_column('accounting_bank_row', sa.Column('internal_category_id', sa.Integer(), nullable=True))
    op.add_column('accounting_bank_row', sa.Column('internal_category_label', sa.Text(), nullable=True))
    op.create_foreign_key(None, 'accounting_bank_row', 'bank_transaction_category_internal', ['internal_category_id'], ['id'])


def downgrade() -> None:
    # 4. Revert accounting_bank_row
    op.drop_constraint(None, 'accounting_bank_row', type_='foreignkey')
    op.drop_column('accounting_bank_row', 'internal_category_label')
    op.drop_column('accounting_bank_row', 'internal_category_id')
    op.drop_column('accounting_bank_row', 'llm_category')

    # 3. Revert accounting_bank_statement
    op.drop_column('accounting_bank_statement', 'raw_header_json')
    op.drop_column('accounting_bank_statement', 'error_message')
    op.drop_column('accounting_bank_statement', 'supabase_path')
    op.drop_column('accounting_bank_statement', 'supabase_bucket')

    # 2. Revert bank_statement_import_run
    op.drop_index('ix_bank_statement_import_run_bank_statement_id', table_name='bank_statement_import_run')
    op.drop_table('bank_statement_import_run')

    # 1. Revert bank_transaction_category_internal
    op.drop_table('bank_transaction_category_internal')
