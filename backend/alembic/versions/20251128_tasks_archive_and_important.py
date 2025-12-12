"""Add is_archived and is_important flags to tasks

Revision ID: tasks_archive_and_important_20251128
Revises: tasks_and_notifications_20251118
Create Date: 2025-11-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "tasks_archive_and_important_20251128"
down_revision: Union[str, Sequence[str], None] = "tasks_and_notifications_20251118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "tasks",
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("tasks", "is_important")
    op.drop_column("tasks", "is_archived")
