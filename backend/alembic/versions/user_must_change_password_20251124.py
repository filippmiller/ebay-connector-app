"""Add must_change_password flag to users for temporary passwords

Revision ID: user_must_change_password_20251124
Revises: security_center_20251124
Create Date: 2025-11-24
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "user_must_change_password_20251124"
down_revision: Union[str, Sequence[str], None] = "security_center_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add must_change_password column to users table."""

    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Drop default after initial backfill; ORM default will apply for new rows.
    op.alter_column("users", "must_change_password", server_default=None)


def downgrade() -> None:
    """Drop must_change_password column from users table (best-effort)."""

    with op.batch_alter_table("users") as batch_op:
        try:
            batch_op.drop_column("must_change_password")
        except Exception:
            # Column might already be absent; ignore errors on downgrade.
            pass
