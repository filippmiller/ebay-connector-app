"""merge heads

Revision ID: e984eafc5e3a
Revises: ebay_scope_definitions_20251114, a1592f74ff82, a655622d4724
Create Date: 2025-11-14 13:20:24.973073

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e984eafc5e3a'
down_revision: Union[str, Sequence[str], None] = ('ebay_scope_definitions_20251114', 'a1592f74ff82', 'a655622d4724')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
