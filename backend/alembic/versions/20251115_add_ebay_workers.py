"""Add tables for eBay workers (state, runs, logs, global config)

Revision ID: ebay_workers_20251115
Revises: ebay_scope_definitions_20251114
Create Date: 2025-11-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'ebay_workers_20251115'
down_revision = 'ebay_scope_definitions_20251114'
branch_labels = None
depends_on = None


def upgrade():
    # ebay_sync_state: per-account, per-API worker configuration and cursor
    op.create_table(
        'ebay_sync_state',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('ebay_account_id', sa.String(length=36), nullable=False),
        sa.Column('ebay_user_id', sa.String(length=64), nullable=False),
        sa.Column('api_family', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('backfill_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cursor_type', sa.String(length=64), nullable=True),
        sa.Column('cursor_value', sa.String(length=64), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('meta', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_ebay_sync_state_account_api', 'ebay_sync_state', ['ebay_account_id', 'api_family'])
    op.create_index('idx_ebay_sync_state_user', 'ebay_sync_state', ['ebay_user_id'])

    # ebay_worker_run: individual executions for locking and status
    op.create_table(
        'ebay_worker_run',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('ebay_account_id', sa.String(length=36), nullable=False),
        sa.Column('ebay_user_id', sa.String(length=64), nullable=False),
        sa.Column('api_family', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary_json', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_ebay_worker_run_account_api', 'ebay_worker_run', ['ebay_account_id', 'api_family'])
    op.create_index('idx_ebay_worker_run_status', 'ebay_worker_run', ['status'])

    # ebay_api_worker_log: detailed log entries per run
    op.create_table(
        'ebay_api_worker_log',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('run_id', sa.String(length=36), sa.ForeignKey('ebay_worker_run.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ebay_account_id', sa.String(length=36), nullable=False),
        sa.Column('ebay_user_id', sa.String(length=64), nullable=False),
        sa.Column('api_family', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('details_json', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_ebay_api_worker_log_run', 'ebay_api_worker_log', ['run_id'])
    op.create_index('idx_ebay_api_worker_log_account_api', 'ebay_api_worker_log', ['ebay_account_id', 'api_family'])
    op.create_index('idx_ebay_api_worker_log_event', 'ebay_api_worker_log', ['event_type'])

    # ebay_worker_global_config: global kill-switch and defaults
    op.create_table(
        'ebay_worker_global_config',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('workers_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('defaults_json', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('ebay_worker_global_config')
    op.drop_index('idx_ebay_api_worker_log_event', table_name='ebay_api_worker_log')
    op.drop_index('idx_ebay_api_worker_log_account_api', table_name='ebay_api_worker_log')
    op.drop_index('idx_ebay_api_worker_log_run', table_name='ebay_api_worker_log')
    op.drop_table('ebay_api_worker_log')
    op.drop_index('idx_ebay_worker_run_status', table_name='ebay_worker_run')
    op.drop_index('idx_ebay_worker_run_account_api', table_name='ebay_worker_run')
    op.drop_table('ebay_worker_run')
    op.drop_index('idx_ebay_sync_state_user', table_name='ebay_sync_state')
    op.drop_index('idx_ebay_sync_state_account_api', table_name='ebay_sync_state')
    op.drop_table('ebay_sync_state')
