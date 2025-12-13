"""Add parts_detail_id link from inventory to parts_detail

Revision ID: inventory_parts_detail_link_20251126
Revises: parts_detail_20251125
Create Date: 2025-11-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "inventory_parts_detail_link_20251126"
down_revision: Union[str, Sequence[str], None] = "parts_detail_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable parts_detail_id column to inventory and index it.

    We keep this as a soft foreign key: the column stores parts_detail.id
    values, and the application enforces consistency. A database-level
    foreign key can be added later if needed.
    """

    op.add_column(
        "inventory",
        sa.Column("parts_detail_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_inventory_parts_detail_id",
        "inventory",
        ["parts_detail_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_inventory_parts_detail_id", table_name="inventory")
    op.drop_column("inventory", "parts_detail_id")
