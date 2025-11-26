"""Deactivate invalid sell.edelivery scope in ebay_scope_definitions

Revision ID: deactivate_sell_edelivery_scope_20251126
Revises: ensure_buy_offer_auction_scope_20251126
Create Date: 2025-11-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "deactivate_sell_edelivery_scope_20251126"
down_revision: Union[str, Sequence[str], None] = "ensure_buy_offer_auction_scope_20251126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TARGET_SCOPE = "https://api.ebay.com/oauth/scope/sell.edelivery"


def upgrade() -> None:
    """Mark the invalid sell.edelivery scope as inactive.

    This scope string has a typo ("/oauth/scope/" instead of
    "/oauth/api_scope/") and causes eBay to return `invalid_scope` when
    included in the authorization URL. We keep the row for historical/audit
    purposes but set is_active = false so it is no longer requested in
    `/ebay/auth/start` flows.
    """
    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE ebay_scope_definitions
            SET is_active = FALSE
            WHERE scope = :scope
            """
        ),
        {"scope": TARGET_SCOPE},
    )


def downgrade() -> None:
    """Re-activate the sell.edelivery scope if needed.

    This simply flips is_active back to true for the same scope value.
    """
    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE ebay_scope_definitions
            SET is_active = TRUE
            WHERE scope = :scope
            """
        ),
        {"scope": TARGET_SCOPE},
    )
