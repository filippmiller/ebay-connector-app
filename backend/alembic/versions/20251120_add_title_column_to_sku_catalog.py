"""add Title column to SKU_catalog

Revision ID: 20251120_add_title_to_sku_catalog
Revises: 20251119_add_parsed_body_to_ebay_messages
Create Date: 2025-11-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251120_add_title_to_sku_catalog"
down_revision: Union[str, None] = "20251119_add_parsed_body_to_ebay_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ensure SKU_catalog has a Title column for the modern SQ form.

    We use `ADD COLUMN IF NOT EXISTS` so the migration is idempotent in
    environments where the column has already been created manually.
    """

    op.execute('ALTER TABLE "SKU_catalog" ADD COLUMN IF NOT EXISTS "Title" text NULL')


def downgrade() -> None:
    """Best-effort downgrade – drop the Title column if present."""

    # `DROP COLUMN IF EXISTS` keeps downgrade safe even if the column was
    # created outside of this migration.
    op.execute('ALTER TABLE "SKU_catalog" DROP COLUMN IF EXISTS "Title"')
