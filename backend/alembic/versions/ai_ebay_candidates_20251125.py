"""Create ai_ebay_candidates table for eBay monitoring worker

Revision ID: ai_ebay_candidates_20251125
Revises: ai_analytics_20251125
Create Date: 2025-11-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ai_ebay_candidates_20251125"
down_revision: Union[str, Sequence[str], None] = "ai_analytics_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ai_ebay_candidates"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("ebay_item_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("shipping", sa.Numeric(14, 2), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("predicted_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("roi", sa.Numeric(10, 4), nullable=True),
        sa.Column("matched_rule", sa.Boolean(), nullable=True),
        sa.Column("rule_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_ai_ebay_candidates_ebay_item_id",
        TABLE_NAME,
        ["ebay_item_id"],
    )
    op.create_index(
        "idx_ai_ebay_candidates_model_id",
        TABLE_NAME,
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_ebay_candidates_model_id", table_name=TABLE_NAME)
    op.drop_constraint("uq_ai_ebay_candidates_ebay_item_id", TABLE_NAME, type_="unique")
    op.drop_table(TABLE_NAME)
