"""Add TEST status to tbl_parts_inventorystatus

Revision ID: 20251209_add_test_status_to_tbl_parts_inventorystatus
Revises: 20251209_add_ebay_listing_test_logs
Create Date: 2025-12-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20251209_add_test_status_to_tbl_parts_inventorystatus"
down_revision: Union[str, Sequence[str], None] = "20251209_add_ebay_listing_test_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert TEST status into tbl_parts_inventorystatus.

    We allocate InventoryStatus_ID as MAX(InventoryStatus_ID) + 1 to avoid
    colliding with existing legacy values.
    """

    conn = op.get_bind()

    # Determine next available InventoryStatus_ID
    max_id = conn.execute(
        text('SELECT MAX("InventoryStatus_ID") FROM "tbl_parts_inventorystatus"')
    ).scalar()
    next_id = int(max_id or 0) + 1

    status_table = sa.table(
        "tbl_parts_inventorystatus",
        sa.column("InventoryStatus_ID", sa.Integer()),
        sa.column("InventoryStatus_Name", sa.Text()),
        sa.column("InventoryShortStatus_Name", sa.Text()),
        sa.column("Color", sa.Text()),
    )

    # Insert TEST status with a distinctive color.
    conn.execute(
        status_table.insert().values(
            InventoryStatus_ID=next_id,
            InventoryStatus_Name="TEST",
            InventoryShortStatus_Name="TEST",
            Color="#ff00ff",
        )
    )


def downgrade() -> None:
    """Remove TEST status row from tbl_parts_inventorystatus."""

    conn = op.get_bind()
    conn.execute(
        text(
            'DELETE FROM "tbl_parts_inventorystatus" '
            'WHERE "InventoryStatus_Name" = :name OR "InventoryShortStatus_Name" = :name'
        ),
        {"name": "TEST"},
    )
