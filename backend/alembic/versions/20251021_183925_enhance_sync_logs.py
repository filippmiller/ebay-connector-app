"""enhance sync_logs table

Revision ID: enhance_sync_logs_001
Revises: 
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa

revision = 'enhance_sync_logs_001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('sync_logs', sa.Column('job_id', sa.String(100), nullable=True))
    op.add_column('sync_logs', sa.Column('pages_fetched', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('sync_logs', sa.Column('records_fetched', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('sync_logs', sa.Column('records_stored', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('sync_logs', sa.Column('duration_ms', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('sync_logs', sa.Column('error_text', sa.Text(), nullable=True))
    
    op.create_index('idx_synclog_job_id', 'sync_logs', ['job_id'], unique=False)

def downgrade():
    op.drop_index('idx_synclog_job_id', table_name='sync_logs')
    op.drop_column('sync_logs', 'error_text')
    op.drop_column('sync_logs', 'duration_ms')
    op.drop_column('sync_logs', 'records_stored')
    op.drop_column('sync_logs', 'records_fetched')
    op.drop_column('sync_logs', 'pages_fetched')
    op.drop_column('sync_logs', 'job_id')
