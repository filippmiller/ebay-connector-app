"""Phase 1: AI Assistant schema catalog and semantic rules

Revision ID: 40c5b8d791ec
Revises: 20251209_add_test_status_to_tbl_parts_inventorystatus
Create Date: 2025-12-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '40c5b8d791ec'
down_revision: Union[str, Sequence[str], None] = '20251209_add_test_status_to_tbl_parts_inventorystatus'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 1 AI Assistant tables."""
    
    # 1. ai_schema_tables - Database schema catalog
    op.create_table(
        'ai_schema_tables',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('schema_name', sa.Text(), nullable=False, server_default='public'),
        sa.Column('table_name', sa.Text(), nullable=False),
        sa.Column('human_title', sa.Text(), nullable=True),
        sa.Column('human_description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('schema_name', 'table_name', name='uq_ai_schema_tables_schema_table'),
    )
    op.create_index('idx_ai_schema_tables_active', 'ai_schema_tables', ['is_active'])
    
    # 2. ai_schema_columns - Column metadata
    op.create_table(
        'ai_schema_columns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('table_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_schema_tables.id', ondelete='CASCADE'), nullable=False),
        sa.Column('column_name', sa.Text(), nullable=False),
        sa.Column('data_type', sa.Text(), nullable=True),
        sa.Column('is_nullable', sa.Boolean(), nullable=True),
        sa.Column('human_title', sa.Text(), nullable=True),
        sa.Column('human_description', sa.Text(), nullable=True),
        sa.Column('example_value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('table_id', 'column_name', name='uq_ai_schema_columns_table_column'),
    )
    op.create_index('idx_ai_schema_columns_table_id', 'ai_schema_columns', ['table_id'])
    
    # 3. ai_semantic_rules - User intent patterns
    op.create_table(
        'ai_semantic_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('locale', sa.Text(), nullable=False, server_default='ru-RU'),
        sa.Column('domain', sa.Text(), nullable=False, server_default='analytics'),
        sa.Column('user_pattern', sa.Text(), nullable=False),
        sa.Column('normalized_intent', sa.Text(), nullable=True),
        sa.Column('target_description', sa.Text(), nullable=True),
        sa.Column('target_sql_template', sa.Text(), nullable=True),
        sa.Column('target_action_type', sa.Text(), nullable=False, server_default='GENERATE_SQL'),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('idx_ai_semantic_rules_domain_locale', 'ai_semantic_rules', ['domain', 'locale'])
    op.create_index('idx_ai_semantic_rules_active', 'ai_semantic_rules', ['is_active'])
    
    # 4. Extend ai_query_log → ai_queries_log
    # First rename
    op.rename_table('ai_query_log', 'ai_queries_log')
    
    # Add new columns
    op.add_column('ai_queries_log', sa.Column('domain', sa.Text(), nullable=True, server_default='analytics'))
    op.add_column('ai_queries_log', sa.Column('input_locale', sa.Text(), nullable=True))
    op.add_column('ai_queries_log', sa.Column('context', postgresql.JSONB(), nullable=True))
    op.add_column('ai_queries_log', sa.Column('used_semantic_rule_id', postgresql.UUID(as_uuid=True), 
                                               sa.ForeignKey('ai_semantic_rules.id', ondelete='SET NULL'), nullable=True))
    op.add_column('ai_queries_log', sa.Column('execution_ok', sa.Boolean(), nullable=True))
    op.add_column('ai_queries_log', sa.Column('execution_result_meta', postgresql.JSONB(), nullable=True))
    op.add_column('ai_queries_log', sa.Column('ai_answer_preview', sa.Text(), nullable=True))
    
    # Add indexes
    op.create_index('idx_ai_queries_log_domain', 'ai_queries_log', ['domain'])
    op.create_index('idx_ai_queries_log_semantic_rule', 'ai_queries_log', ['used_semantic_rule_id'])


def downgrade() -> None:
    """Drop Phase 1 AI Assistant tables."""
    
    # Drop indexes
    op.drop_index('idx_ai_queries_log_semantic_rule', table_name='ai_queries_log')
    op.drop_index('idx_ai_queries_log_domain', table_name='ai_queries_log')
    
    # Remove added columns
    op.drop_column('ai_queries_log', 'ai_answer_preview')
    op.drop_column('ai_queries_log', 'execution_result_meta')
    op.drop_column('ai_queries_log', 'execution_ok')
    op.drop_column('ai_queries_log', 'used_semantic_rule_id')
    op.drop_column('ai_queries_log', 'context')
    op.drop_column('ai_queries_log', 'input_locale')
    op.drop_column('ai_queries_log', 'domain')
    
    # Rename back
    op.rename_table('ai_queries_log', 'ai_query_log')
    
    # Drop new tables
    op.drop_index('idx_ai_semantic_rules_active', table_name='ai_semantic_rules')
    op.drop_index('idx_ai_semantic_rules_domain_locale', table_name='ai_semantic_rules')
    op.drop_table('ai_semantic_rules')
    
    op.drop_index('idx_ai_schema_columns_table_id', table_name='ai_schema_columns')
    op.drop_table('ai_schema_columns')
    
    op.drop_index('idx_ai_schema_tables_active', table_name='ai_schema_tables')
    op.drop_table('ai_schema_tables')
