"""Add tasks, task_comments, and task_notifications tables

Revision ID: tasks_and_notifications_20251118
Revises: user_grid_layouts_theme_20251118
Create Date: 2025-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "tasks_and_notifications_20251118"
down_revision: Union[str, Sequence[str], None] = "user_grid_layouts_theme_20251118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create main tasks table (used for both tasks and reminders)
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),  # 'task' or 'reminder'
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("creator_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignee_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_popup", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("idx_tasks_assignee_status", "tasks", ["assignee_id", "status"])
    op.create_index("idx_tasks_creator_status", "tasks", ["creator_id", "status"])
    op.create_index("idx_tasks_type_status", "tasks", ["type", "status"])
    op.create_index("idx_tasks_due_at", "tasks", ["due_at"])

    # Comments & activity timeline (user + system)
    op.create_table(
        "task_comments",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False, server_default="comment"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_task_comments_task_id", "task_comments", ["task_id"])
    op.create_index("idx_task_comments_author_id", "task_comments", ["author_id"])

    # Per-user notifications powering bell & popups
    op.create_table(
        "task_notifications",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unread"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_task_notifications_user_status_created",
        "task_notifications",
        ["user_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_task_notifications_user_status_created", table_name="task_notifications")
    op.drop_table("task_notifications")

    op.drop_index("idx_task_comments_author_id", table_name="task_comments")
    op.drop_index("idx_task_comments_task_id", table_name="task_comments")
    op.drop_table("task_comments")

    op.drop_index("idx_tasks_due_at", table_name="tasks")
    op.drop_index("idx_tasks_type_status", table_name="tasks")
    op.drop_index("idx_tasks_creator_status", table_name="tasks")
    op.drop_index("idx_tasks_assignee_status", table_name="tasks")
    op.drop_table("tasks")
