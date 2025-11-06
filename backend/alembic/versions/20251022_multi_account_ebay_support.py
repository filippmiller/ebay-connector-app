"""Add multi-account eBay support tables

Revision ID: multi_account_001
Revises: enhance_inventory_001
Create Date: 2025-10-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

revision = 'multi_account_001'
down_revision = 'enhance_inventory_001'
branch_labels = None
depends_on = None

def upgrade():
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Check if table already exists
    existing_tables = inspector.get_table_names()
    
    # Get existing indexes
    existing_indexes = {}
    for table_name in existing_tables:
        existing_indexes[table_name] = [idx['name'] for idx in inspector.get_indexes(table_name)]
    
    if 'ebay_accounts' not in existing_tables:
        op.create_table(
            'ebay_accounts',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('org_id', sa.String(36), nullable=False),
            sa.Column('ebay_user_id', sa.Text(), nullable=False),
            sa.Column('username', sa.Text(), nullable=True),
            sa.Column('house_name', sa.Text(), nullable=False),
            sa.Column('purpose', sa.Text(), nullable=True, server_default='BOTH'),
            sa.Column('marketplace_id', sa.Text(), nullable=True),
            sa.Column('site_id', sa.Integer(), nullable=True),
            sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['org_id'], ['users.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_ebay_accounts_org_id', 'ebay_accounts', ['org_id'])
        op.create_index('idx_ebay_accounts_ebay_user_id', 'ebay_accounts', ['ebay_user_id'])
        op.create_index('idx_ebay_accounts_house_name', 'ebay_accounts', ['house_name'])
        op.create_index('idx_ebay_accounts_is_active', 'ebay_accounts', ['is_active'])
        op.execute('CREATE UNIQUE INDEX idx_ebay_accounts_org_ebay_user ON ebay_accounts (org_id, ebay_user_id)')
        op.execute('CREATE UNIQUE INDEX idx_ebay_accounts_org_house_name ON ebay_accounts (org_id, house_name) WHERE is_active = TRUE')
    else:
        # Update indexes list if table exists
        existing_indexes['ebay_accounts'] = [idx['name'] for idx in inspector.get_indexes('ebay_accounts')]
        if 'idx_ebay_accounts_org_id' not in existing_indexes['ebay_accounts']:
            op.create_index('idx_ebay_accounts_org_id', 'ebay_accounts', ['org_id'])
        if 'idx_ebay_accounts_ebay_user_id' not in existing_indexes['ebay_accounts']:
            op.create_index('idx_ebay_accounts_ebay_user_id', 'ebay_accounts', ['ebay_user_id'])
        if 'idx_ebay_accounts_house_name' not in existing_indexes['ebay_accounts']:
            op.create_index('idx_ebay_accounts_house_name', 'ebay_accounts', ['house_name'])
        if 'idx_ebay_accounts_is_active' not in existing_indexes['ebay_accounts']:
            op.create_index('idx_ebay_accounts_is_active', 'ebay_accounts', ['is_active'])
        if 'idx_ebay_accounts_org_ebay_user' not in existing_indexes['ebay_accounts']:
            op.execute('CREATE UNIQUE INDEX idx_ebay_accounts_org_ebay_user ON ebay_accounts (org_id, ebay_user_id)')
        if 'idx_ebay_accounts_org_house_name' not in existing_indexes['ebay_accounts']:
            op.execute('CREATE UNIQUE INDEX idx_ebay_accounts_org_house_name ON ebay_accounts (org_id, house_name) WHERE is_active = TRUE')
    
    if 'ebay_tokens' not in existing_tables:
        op.create_table(
            'ebay_tokens',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('ebay_account_id', sa.String(36), nullable=False),
            sa.Column('access_token', sa.Text(), nullable=True),
            sa.Column('refresh_token', sa.Text(), nullable=True),
            sa.Column('token_type', sa.Text(), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_refreshed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('refresh_error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_ebay_tokens_account_id', 'ebay_tokens', ['ebay_account_id'])
        op.create_index('idx_ebay_tokens_expires_at', 'ebay_tokens', ['expires_at'])
    
    if 'ebay_authorizations' not in existing_tables:
        op.create_table(
            'ebay_authorizations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('ebay_account_id', sa.String(36), nullable=False),
            sa.Column('scopes', ARRAY(sa.Text()), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_ebay_authorizations_account_id', 'ebay_authorizations', ['ebay_account_id'])
    
    if 'ebay_sync_cursors' not in existing_tables:
        op.create_table(
            'ebay_sync_cursors',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('ebay_account_id', sa.String(36), nullable=False),
            sa.Column('resource', sa.Text(), nullable=False),
            sa.Column('checkpoint', JSONB, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_ebay_sync_cursors_account_id', 'ebay_sync_cursors', ['ebay_account_id'])
        op.create_index('idx_ebay_sync_cursors_resource', 'ebay_sync_cursors', ['resource'])
        op.execute('CREATE UNIQUE INDEX idx_ebay_sync_cursors_account_resource ON ebay_sync_cursors (ebay_account_id, resource)')
    
    if 'ebay_health_events' not in existing_tables:
        op.create_table(
            'ebay_health_events',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('ebay_account_id', sa.String(36), nullable=False),
            sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('is_healthy', sa.Boolean(), nullable=False),
            sa.Column('http_status', sa.Integer(), nullable=True),
            sa.Column('ack', sa.Text(), nullable=True),
            sa.Column('error_code', sa.Text(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('response_time_ms', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_ebay_health_events_account_id', 'ebay_health_events', ['ebay_account_id'])
        op.create_index('idx_ebay_health_events_checked_at', 'ebay_health_events', ['checked_at'])
        op.create_index('idx_ebay_health_events_is_healthy', 'ebay_health_events', ['is_healthy'])


def downgrade():
    op.drop_table('ebay_health_events')
    op.drop_table('ebay_sync_cursors')
    op.drop_table('ebay_authorizations')
    op.drop_table('ebay_tokens')
    op.drop_table('ebay_accounts')
