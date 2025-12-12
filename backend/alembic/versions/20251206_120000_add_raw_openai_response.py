"""add raw_openai_response to accounting_bank_statement

Revision ID: 20251206_120000
Revises: 3aa605dd5982
Create Date: 2025-12-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251206_120000'
down_revision: Union[str, Sequence[str], None] = '3aa605dd5982'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounting_bank_statement', sa.Column('raw_openai_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('accounting_bank_statement', 'raw_openai_response')
