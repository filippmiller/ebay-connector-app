"""Add fire_at and comment columns to ebay_snipes for precise scheduling

Revision ID: ebay_snipes_fire_at_comment_20251125
Revises: ebay_snipes_20251124
Create Date: 2025-11-25

This migration extends the ebay_snipes table used by the internal
"Sniper/Bidnapper" module with:
- fire_at: explicit execution timestamp (end_time - seconds_before_end)
- comment: optional user-provided note

NOTE: Do NOT run this migration until DATABASE_URL for the production
Supabase Postgres is valid and Alembic can connect without tenant/user
errors.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ebay_snipes_fire_at_comment_20251125"
down_revision: Union[str, Sequence[str], None] = "ebay_snipes_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ebay_snipes"


def upgrade() -> None:
    """Add fire_at and comment columns to ebay_snipes.

    fire_at is the exact scheduled execution time for the snipe, computed as
    end_time - seconds_before_end. Storing it explicitly makes scheduling
    queries simpler and more precise, and allows us to index directly on the
    execution timestamp instead of recomputing it on every worker tick.
    """

    # 1) Add columns as nullable to allow backfill in a single migration.
    op.add_column(
        TABLE_NAME,
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("fire_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2) Best-effort backfill of fire_at for existing rows.
    #
    # We intentionally keep this as a single SQL expression so that it runs
    # close to the database and does not depend on application-level enums.
    conn = op.get_bind()
    # Use a textual UPDATE to avoid reflection; end_time is NOT NULL and
    # seconds_before_end has a server default, so fire_at should be
    # well-defined for all existing rows.
    conn.execute(
        sa.text(
            """
            UPDATE ebay_snipes
            SET fire_at = end_time - (make_interval(secs := seconds_before_end))
            WHERE fire_at IS NULL
            """
        )
    )

    # 3) Make fire_at non-nullable and index it for worker queries.
    op.alter_column(TABLE_NAME, "fire_at", nullable=False)
    op.create_index("idx_ebay_snipes_fire_at", TABLE_NAME, ["fire_at"])


def downgrade() -> None:
    """Drop fire_at and comment columns (best-effort)."""

    op.drop_index("idx_ebay_snipes_fire_at", table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, "fire_at")
    op.drop_column(TABLE_NAME, "comment")
