"""Ensure commerce.identity.readonly scope is active in ebay_scope_definitions

Revision ID: ensure_commerce_identity_scope_20251120
Revises: ebay_events_20251119
Create Date: 2025-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from uuid import uuid4

# revision identifiers, used by Alembic.
revision: str = "ensure_commerce_identity_scope_20251120"
down_revision: Union[str, Sequence[str], None] = "ebay_events_20251119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCOPE_VALUE = "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly"
DESCRIPTION = (
    "View a user's basic information, such as username or business account details, "
    "from their eBay member account"
)


def upgrade() -> None:
    """Idempotently ensure commerce.identity.readonly exists and is active.

    This migration is safe to run multiple times. If the row already exists,
    we simply enforce grant_type='user' and is_active=true. If it does not
    exist, we insert it with a new UUID primary key.
    """

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "ebay_scope_definitions" not in tables:
        # Scope catalog table not present; nothing to do.
        return

    row = conn.execute(
        text(
            "SELECT id, grant_type, is_active FROM ebay_scope_definitions "
            "WHERE scope = :scope"
        ),
        {"scope": SCOPE_VALUE},
    ).fetchone()

    if row is None:
        conn.execute(
            text(
                """
                INSERT INTO ebay_scope_definitions (
                    id, scope, description, grant_type, is_active, meta, created_at, updated_at
                ) VALUES (:id, :scope, :description, :grant_type, :is_active, NULL, NOW(), NOW())
                """
            ),
            {
                "id": str(uuid4()),
                "scope": SCOPE_VALUE,
                "description": DESCRIPTION,
                "grant_type": "user",
                "is_active": True,
            },
        )
    else:
        conn.execute(
            text(
                """
                UPDATE ebay_scope_definitions
                SET grant_type = :grant_type,
                    is_active = :is_active,
                    updated_at = NOW()
                WHERE scope = :scope
                """
            ),
            {
                "scope": SCOPE_VALUE,
                "grant_type": "user",
                "is_active": True,
            },
        )


def downgrade() -> None:
    """No-op downgrade.

    We intentionally do not delete the scope row on downgrade to avoid
    accidentally breaking existing tokens or admin tooling that depends on
    this catalog entry.
    """
    # Intentionally left blank.
    pass
