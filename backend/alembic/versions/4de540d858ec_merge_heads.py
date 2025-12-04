"""merge heads

Revision ID: 4de540d858ec
Revises: 20251204_add_worker_notifications_enabled, accounting_pipeline_20251203, f27bfdb8a340
Create Date: 2025-12-04 11:35:42.237379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4de540d858ec'
down_revision: Union[str, Sequence[str], None] = ('20251204_add_worker_notifications_enabled', 'accounting_pipeline_20251203', 'f27bfdb8a340')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
