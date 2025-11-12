"""merge heads

Revision ID: 44ddab237a3a
Revises: add_raw_payload_line_items, add_core_ops_tables, ebay_connect_logs_001
Create Date: 2025-11-12 01:12:28.176443

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44ddab237a3a'
down_revision: Union[str, Sequence[str], None] = ('add_raw_payload_line_items', 'add_core_ops_tables', 'ebay_connect_logs_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
