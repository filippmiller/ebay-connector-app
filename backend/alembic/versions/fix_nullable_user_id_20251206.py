"""Allow null created_by_user_id for script imports

Revision ID: fix_nullable_user_id_20251206
Revises: bank_statement_v1_20251206
Create Date: 2025-12-06 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_nullable_user_id_20251206'
down_revision: Union[str, Sequence[str], None] = 'bank_statement_v1_20251206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make created_by_user_id nullable in accounting_bank_statement
    op.alter_column('accounting_bank_statement', 'created_by_user_id',
                    existing_type=sa.String(36),
                    nullable=True)


def downgrade() -> None:
    # Revert to non-nullable (may fail if there are null values)
    op.alter_column('accounting_bank_statement', 'created_by_user_id',
                    existing_type=sa.String(36),
                    nullable=False)
