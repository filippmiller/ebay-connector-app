"""merge multiple heads

Revision ID: f27bfdb8a340
Revises: tasks_archive_and_important_20251128, token_refresh_visibility_20251129, add_source_to_ebay_connect_logs_20251201, add_inventory_offers_20251203, ai_providers_openai_20251126, deactivate_sell_edelivery_scope_20251126, ebay_search_watches_20251128, gmail_integrations_20251125, timesheets_open_timer_20251124, user_is_active_20251124
Create Date: 2025-12-03 09:28:58.431560

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f27bfdb8a340'
down_revision: Union[str, Sequence[str], None] = ('tasks_archive_and_important_20251128', 'token_refresh_visibility_20251129', 'add_source_to_ebay_connect_logs_20251201', 'add_inventory_offers_20251203', 'ai_providers_openai_20251126', 'deactivate_sell_edelivery_scope_20251126', 'ebay_search_watches_20251128', 'gmail_integrations_20251125', 'timesheets_open_timer_20251124', 'user_is_active_20251124')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
