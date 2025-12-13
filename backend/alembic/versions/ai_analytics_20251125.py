"""Add ai_rules and ai_query_log tables for AI analytics engine

Revision ID: ai_analytics_20251125
Revises: ebay_snipe_logs_20251125
Create Date: 2025-11-25

This migration introduces two tables used by the Admin AI Grid / AI Rules
features:

- ai_rules: stores reusable SQL rule fragments generated from natural language.
- ai_query_log: append-only log of executed AI analytics queries.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ai_analytics_20251125"
down_revision: Union[str, Sequence[str], None] = "ebay_snipe_logs_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ai_rules and ai_query_log tables."""

    # ai_rules: reusable SQL rule fragments (e.g. profitability conditions)
    op.create_table(
        "ai_rules",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rule_sql", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_ai_rules_user"),
    )

    # Minimal index on creation time to support recent-rules listings.
    op.create_index(
        "idx_ai_rules_created_at",
        "ai_rules",
        ["created_at"],
    )

    # ai_query_log: append-only log of AI-generated SQL queries executed by admins
    op.create_table(
        "ai_query_log",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ai_query_log_user"),
    )

    op.create_index(
        "idx_ai_query_log_user",
        "ai_query_log",
        ["user_id"],
    )
    op.create_index(
        "idx_ai_query_log_executed_at",
        "ai_query_log",
        ["executed_at"],
    )


def downgrade() -> None:
    """Drop AI analytics tables (best-effort)."""

    op.drop_index("idx_ai_query_log_executed_at", table_name="ai_query_log")
    op.drop_index("idx_ai_query_log_user", table_name="ai_query_log")
    op.drop_table("ai_query_log")

    op.drop_index("idx_ai_rules_created_at", table_name="ai_rules")
    op.drop_table("ai_rules")
