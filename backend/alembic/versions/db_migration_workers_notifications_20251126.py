"""Add owner and notification flags to db_migration_workers

Revision ID: db_migration_workers_notifications_20251126
Revises: db_migration_workers_20251126
Create Date: 2025-11-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "db_migration_workers_notifications_20251126"
down_revision: Union[str, Sequence[str], None] = "db_migration_workers_20251126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add owner_user_id and notification flags (idempotent)."""

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "db_migration_workers" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("db_migration_workers")}

    if "owner_user_id" not in columns:
        op.add_column(
            "db_migration_workers",
            sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        )

    if "notify_on_success" not in columns:
        op.add_column(
            "db_migration_workers",
            sa.Column("notify_on_success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if "notify_on_error" not in columns:
        op.add_column(
            "db_migration_workers",
            sa.Column("notify_on_error", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )


def downgrade() -> None:
    """Drop notification-related columns (best-effort)."""

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "db_migration_workers" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("db_migration_workers")}

    if "notify_on_error" in columns:
        op.drop_column("db_migration_workers", "notify_on_error")
    if "notify_on_success" in columns:
        op.drop_column("db_migration_workers", "notify_on_success")
    if "owner_user_id" in columns:
        op.drop_column("db_migration_workers", "owner_user_id")
