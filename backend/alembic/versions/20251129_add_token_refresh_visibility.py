"""Add background worker + token refresh log tables

Revision ID: token_refresh_visibility_20251129
Revises: ebay_events_20251119
Create Date: 2025-11-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "token_refresh_visibility_20251129"
down_revision: Union[str, Sequence[str], None] = "ebay_events_20251119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create background_workers and ebay_token_refresh_log tables."""

    # Generic background worker heartbeat/status table
    op.create_table(
        "background_workers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("worker_name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("runs_ok_in_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runs_error_in_row", sa.Integer(), nullable=False, server_default="0"),
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
    op.create_index(
        "idx_background_workers_name", "background_workers", ["worker_name"], unique=True
    )

    # Per-account token refresh attempt log
    op.create_table(
        "ebay_token_refresh_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "ebay_account_id",
            sa.String(length=36),
            sa.ForeignKey("ebay_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("old_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_ebay_token_refresh_log_account_time",
        "ebay_token_refresh_log",
        ["ebay_account_id", "started_at"],
    )


def downgrade() -> None:
    """Drop background_workers and ebay_token_refresh_log tables."""
    op.drop_index(
        "idx_ebay_token_refresh_log_account_time",
        table_name="ebay_token_refresh_log",
    )
    op.drop_table("ebay_token_refresh_log")

    op.drop_index("idx_background_workers_name", table_name="background_workers")
    op.drop_table("background_workers")
