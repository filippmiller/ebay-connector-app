"""Add theme column to user_grid_layouts

Revision ID: user_grid_layouts_theme_20251118
Revises: user_grid_layouts_20251115
Create Date: 2025-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "user_grid_layouts_theme_20251118"
down_revision: Union[str, Sequence[str], None] = "user_grid_layouts_20251115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_grid_layouts",
        sa.Column(
            "theme",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_grid_layouts", "theme")
