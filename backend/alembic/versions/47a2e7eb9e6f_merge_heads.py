"""merge heads

Revision ID: 47a2e7eb9e6f
Revises: ebay_finances_20251117, timesheets_001, accounting_20251118, dae483e3dc8c, ebay_buyer_001, ui_tweak_settings_20251121
Create Date: 2025-11-23 09:21:25.516884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47a2e7eb9e6f'
down_revision: Union[str, Sequence[str], None] = ('ebay_finances_20251117', 'timesheets_001', 'accounting_20251118', 'dae483e3dc8c', 'ebay_buyer_001', 'ui_tweak_settings_20251121')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
