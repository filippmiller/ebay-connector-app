"""Add sandbox tokens to users table

Revision ID: sandbox_tokens_001
Revises: multi_account_001
Create Date: 2025-11-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'sandbox_tokens_001'
down_revision = 'multi_account_001'
branch_labels = None
depends_on = None

def upgrade():
    """Add sandbox token columns to users table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Check if columns already exist
    if 'users' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'ebay_sandbox_access_token' not in existing_columns:
            op.add_column('users', sa.Column('ebay_sandbox_access_token', sa.Text(), nullable=True))
        
        if 'ebay_sandbox_refresh_token' not in existing_columns:
            op.add_column('users', sa.Column('ebay_sandbox_refresh_token', sa.Text(), nullable=True))
        
        if 'ebay_sandbox_token_expires_at' not in existing_columns:
            op.add_column('users', sa.Column('ebay_sandbox_token_expires_at', sa.DateTime(), nullable=True))

def downgrade():
    """Remove sandbox token columns from users table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if 'users' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'ebay_sandbox_token_expires_at' in existing_columns:
            op.drop_column('users', 'ebay_sandbox_token_expires_at')
        
        if 'ebay_sandbox_refresh_token' in existing_columns:
            op.drop_column('users', 'ebay_sandbox_refresh_token')
        
        if 'ebay_sandbox_access_token' in existing_columns:
            op.drop_column('users', 'ebay_sandbox_access_token')

