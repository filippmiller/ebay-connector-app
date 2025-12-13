"""Add worker_notifications_enabled to users table

Revision ID: 20251204_add_worker_notifications_enabled
Revises: 20251203_add_inventory_offers
Create Date: 2025-12-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251204_add_worker_notifications_enabled"
down_revision: Union[str, Sequence[str], None] = "add_inventory_offers_20251203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "worker_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "worker_notifications_enabled")
