"""Add security_events, login_attempts, and security_settings tables

Revision ID: security_center_20251124
Revises: ebay_inquiries_20251124
Create Date: 2025-11-24

This migration introduces three tables used by the Security Center:

- security_events: append-only log of security-relevant events.
- login_attempts: canonical record of each login attempt and block decision.
- security_settings: singleton configuration row for brute-force and session policy.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "security_center_20251124"
down_revision: Union[str, Sequence[str], None] = "ebay_inquiries_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create security_events, login_attempts, and security_settings tables.

    Also adds the must_change_password flag to users to support temporary
    passwords and forced change on first login.
    """

    # Add must_change_password flag to users
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Drop default after backfill; new rows will rely on ORM default.
    op.alter_column("users", "must_change_password", server_default=None)

    # security_events: append-only security log
    op.create_table(
        "security_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_security_events_user"),
    )
    op.create_index(
        "idx_security_events_user_time",
        "security_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_security_events_ip_time",
        "security_events",
        ["ip_address", "created_at"],
    )
    op.create_index(
        "idx_security_events_event_type",
        "security_events",
        ["event_type"],
    )

    # login_attempts: individual login attempts and block decisions
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column(
            "block_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("block_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_login_attempts_user"),
    )
    op.create_index(
        "idx_login_attempts_email",
        "login_attempts",
        ["email"],
    )
    op.create_index(
        "idx_login_attempts_user_id",
        "login_attempts",
        ["user_id"],
    )
    op.create_index(
        "idx_login_attempts_email_ip_time",
        "login_attempts",
        ["email", "ip_address", "created_at"],
    )

    # security_settings: singleton configuration row for brute-force + sessions
    op.create_table(
        "security_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "max_failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "initial_block_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "progressive_delay_step_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column(
            "max_delay_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "enable_captcha",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "captcha_after_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "session_ttl_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text(str(60 * 12)),  # 12 hours
        ),
        sa.Column(
            "session_idle_timeout_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column(
            "bruteforce_alert_threshold_per_ip",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("50"),
        ),
        sa.Column(
            "bruteforce_alert_threshold_per_user",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("50"),
        ),
        sa.Column(
            "alert_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("alert_channel", sa.String(length=50), nullable=True),
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
        "idx_security_settings_updated_at",
        "security_settings",
        ["updated_at"],
    )


def downgrade() -> None:
    """Drop security tables (best-effort)."""

    # Drop in reverse dependency order
    op.drop_index("idx_security_settings_updated_at", table_name="security_settings")
    op.drop_table("security_settings")

    op.drop_index("idx_login_attempts_email_ip_time", table_name="login_attempts")
    op.drop_index("idx_login_attempts_user_id", table_name="login_attempts")
    op.drop_index("idx_login_attempts_email", table_name="login_attempts")
    op.drop_table("login_attempts")

    op.drop_index("idx_security_events_event_type", table_name="security_events")
    op.drop_index("idx_security_events_ip_time", table_name="security_events")
    op.drop_index("idx_security_events_user_time", table_name="security_events")
    op.drop_table("security_events")
