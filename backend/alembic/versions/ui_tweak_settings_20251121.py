"""Add ui_tweak_settings table for global UI tweak configuration

Revision ID: ui_tweak_settings_20251121
Revises: shipping_tables_20251121
Create Date: 2025-11-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "ui_tweak_settings_20251121"
down_revision: Union[str, Sequence[str], None] = "shipping_tables_20251121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ui_tweak_settings"


DEFAULT_SETTINGS = {
    "fontScale": 1.0,
    "navScale": 1.0,
    "gridDensity": "compact",
    "gridFontFamily": '"Tahoma","Segoe UI",Arial,sans-serif',
    "navActiveBg": "#2563eb",
    "navActiveText": "#ffffff",
    "navInactiveBg": "transparent",
    "navInactiveText": "#374151",
}


def upgrade() -> None:
    """Create ui_tweak_settings table if it does not exist and seed defaults."""

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_tables = set(inspector.get_table_names())
    if TABLE_NAME not in existing_tables:
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        existing_tables.add(TABLE_NAME)

    # Seed a single default row if the table is empty.
    if TABLE_NAME in existing_tables:
        result = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE_NAME}"))
        count = result.scalar_one()
        if not count:
            conn.execute(
                sa.text(
                    f"INSERT INTO {TABLE_NAME} (settings) VALUES (:settings)",
                ),
                {"settings": DEFAULT_SETTINGS},
            )


def downgrade() -> None:
    """Drop ui_tweak_settings table (best-effort)."""

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if TABLE_NAME in existing_tables:
        op.drop_table(TABLE_NAME)
