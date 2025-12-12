"""Add config fields to background_workers and seed inventory_mv_refresh worker

Revision ID: 20251209_add_inventory_mv_worker_settings
Revises: classification_codes_20251206
Create Date: 2025-12-09

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20251209_add_inventory_mv_worker_settings"
down_revision: Union[str, Sequence[str], None] = "classification_codes_20251206"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend background_workers with minimal configuration fields that can be
    # reused by generic workers such as the inventory MV refresh loop.
    op.add_column(
        "background_workers",
        sa.Column(
            "display_name",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "background_workers",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "background_workers",
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # Seed a default row for the inventory MV refresh worker if it does not
    # already exist. This worker uses ``worker_name = 'inventory_mv_refresh'``
    # as its stable key.
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM background_workers WHERE worker_name = :name"),
        {"name": "inventory_mv_refresh"},
    ).first()

    if result is None:
        workers_table = sa.table(
            "background_workers",
            sa.column("id", sa.String(36)),
            sa.column("worker_name", sa.String(128)),
            sa.column("display_name", sa.Text()),
            sa.column("description", sa.Text()),
            sa.column("enabled", sa.Boolean()),
            sa.column("interval_seconds", sa.Integer()),
        )

        conn.execute(
            workers_table.insert().values(
                id=str(uuid.uuid4()),
                worker_name="inventory_mv_refresh",
                display_name="Inventory MV Refresh",
                description=(
                    "Refreshes inventory materialized views used by the Inventory V3 "
                    "grid (SKU/ItemID Active/Sold counters)."
                ),
                enabled=True,
                interval_seconds=600,
            )
        )


def downgrade() -> None:
    # Dropping columns will implicitly drop the seeded row's extra metadata,
    # but we do not attempt to delete any specific worker row here.
    op.drop_column("background_workers", "enabled")
    op.drop_column("background_workers", "description")
    op.drop_column("background_workers", "display_name")
