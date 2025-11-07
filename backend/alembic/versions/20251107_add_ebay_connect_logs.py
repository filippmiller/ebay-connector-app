"""Add eBay connect logs table

Revision ID: ebay_connect_logs_001
Revises: sandbox_tokens_001
Create Date: 2025-11-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'ebay_connect_logs_001'
down_revision = 'sandbox_tokens_001'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if 'ebay_connect_logs' not in inspector.get_table_names():
        op.create_table(
            'ebay_connect_logs',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('environment', sa.String(length=20), nullable=False, server_default='sandbox'),
            sa.Column('action', sa.String(length=50), nullable=False),
            sa.Column('request_method', sa.String(length=10), nullable=True),
            sa.Column('request_url', sa.Text(), nullable=True),
            sa.Column('request_headers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('request_body', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('response_status', sa.Integer(), nullable=True),
            sa.Column('response_headers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('idx_ebay_connect_logs_user_env', 'ebay_connect_logs', ['user_id', 'environment'])
        op.create_index('idx_ebay_connect_logs_action', 'ebay_connect_logs', ['action'])
        op.create_index('idx_ebay_connect_logs_created', 'ebay_connect_logs', ['created_at'])


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if 'ebay_connect_logs' in inspector.get_table_names():
        op.drop_index('idx_ebay_connect_logs_created', table_name='ebay_connect_logs')
        op.drop_index('idx_ebay_connect_logs_action', table_name='ebay_connect_logs')
        op.drop_index('idx_ebay_connect_logs_user_env', table_name='ebay_connect_logs')
        op.drop_table('ebay_connect_logs')

