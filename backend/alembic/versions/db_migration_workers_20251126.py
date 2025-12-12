"""Add db_migration_workers table for MSSQL→Supabase workers

Revision ID: db_migration_workers_20251126
Revises: ensure_buy_offer_auction_scope_20251126
Create Date: 2025-11-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "db_migration_workers_20251126"
down_revision: Union[str, Sequence[str], None] = "ensure_buy_offer_auction_scope_20251126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create db_migration_workers table (idempotent).

    This table stores configuration and last-run metadata for MSSQL→Supabase
    incremental workers operating on append-only tables keyed by a single
    primary key column.
    """

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "db_migration_workers" in tables:
        return

    op.create_table(
        "db_migration_workers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_database", sa.String(length=255), nullable=False),
        sa.Column("source_schema", sa.String(length=128), nullable=False),
        sa.Column("source_table", sa.String(length=255), nullable=False),
        sa.Column("target_schema", sa.String(length=128), nullable=False),
        sa.Column("target_table", sa.String(length=255), nullable=False),
        sa.Column("pk_column", sa.String(length=255), nullable=False),
        sa.Column("worker_enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("last_run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_source_row_count", sa.BigInteger(), nullable=True),
        sa.Column("last_target_row_count", sa.BigInteger(), nullable=True),
        sa.Column("last_inserted_count", sa.BigInteger(), nullable=True),
        sa.Column("last_max_pk_source", sa.BigInteger(), nullable=True),
        sa.Column("last_max_pk_target", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_database",
            "source_schema",
            "source_table",
            "target_schema",
            "target_table",
            name="uq_db_migration_workers_source_target",
        ),
    )

    op.create_index(
        "idx_db_migration_workers_enabled",
        "db_migration_workers",
        ["worker_enabled"],
    )


def downgrade() -> None:
    """Drop db_migration_workers table (best-effort)."""

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "db_migration_workers" not in tables:
        return

    op.drop_index("idx_db_migration_workers_enabled", table_name="db_migration_workers")
    op.drop_table("db_migration_workers")
