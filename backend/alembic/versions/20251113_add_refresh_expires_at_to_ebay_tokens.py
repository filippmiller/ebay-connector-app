"""Add refresh_expires_at to ebay_tokens

Revision ID: add_refresh_expires_at_20251113
Revises: ebay_connect_logs_001
Create Date: 2025-11-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'add_refresh_expires_at_20251113'
down_revision = 'ebay_connect_logs_001'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = []
    try:
        cols = [c['name'] for c in inspector.get_columns('ebay_tokens')]
    except Exception:
        pass
    if 'refresh_expires_at' not in cols:
        op.add_column('ebay_tokens', sa.Column('refresh_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = []
    try:
        cols = [c['name'] for c in inspector.get_columns('ebay_tokens')]
    except Exception:
        pass
    if 'refresh_expires_at' in cols:
        op.drop_column('ebay_tokens', 'refresh_expires_at')
