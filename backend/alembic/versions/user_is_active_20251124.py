"""Add is_active flag to users for soft deactivation

Revision ID: user_is_active_20251124
Revises: user_must_change_password_20251124
Create Date: 2025-11-24
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "user_is_active_20251124"
down_revision: Union[str, Sequence[str], None] = "user_must_change_password_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_active column to users table for soft deactivation."""

    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Drop default after initial backfill; ORM default will apply for new rows.
    op.alter_column("users", "is_active", server_default=None)


def downgrade() -> None:
    """Drop is_active column from users table (best-effort)."""

    with op.batch_alter_table("users") as batch_op:
        try:
            batch_op.drop_column("is_active")
        except Exception:
            # Column might already be absent; ignore errors on downgrade.
            pass
