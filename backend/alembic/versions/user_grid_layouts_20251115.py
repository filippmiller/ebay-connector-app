"""Add per-user grid layout table

Revision ID: user_grid_layouts_20251115
Revises: ebay_identity_20251115
Create Date: 2025-11-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "user_grid_layouts_20251115"
down_revision: Union[str, Sequence[str], None] = "ebay_identity_20251115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_grid_layouts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("grid_key", sa.String(length=100), nullable=False),
        sa.Column("visible_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("column_widths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sort", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_user_grid_layouts_user_grid",
        "user_grid_layouts",
        ["user_id", "grid_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_user_grid_layouts_user_grid", table_name="user_grid_layouts")
    op.drop_table("user_grid_layouts")