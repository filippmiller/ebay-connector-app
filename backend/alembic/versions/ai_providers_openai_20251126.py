"""Add ai_providers table for AI provider config (OpenAI)

Revision ID: ai_providers_openai_20251126
Revises: ensure_buy_offer_auction_scope_20251126
Create Date: 2025-11-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ai_providers_openai_20251126"
down_revision: Union[str, Sequence[str], None] = "ensure_buy_offer_auction_scope_20251126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ai_providers table for storing AI provider configuration.

    The table is intentionally generic so we can support multiple providers
    (OpenAI, Anthropic, etc.) in the future. For now only provider_code
    "openai" will be used by the application.
    """

    op.create_table(
        "ai_providers",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("model_default", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_ai_providers_owner_user_id",
        "ai_providers",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_providers_owner_user_id", table_name="ai_providers")
    op.drop_table("ai_providers")
