"""merge heads

Revision ID: a1592f74ff82
Revises: 44ddab237a3a
Create Date: 2025-11-12 01:22:29.789393

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1592f74ff82'
down_revision: Union[str, Sequence[str], None] = '44ddab237a3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
