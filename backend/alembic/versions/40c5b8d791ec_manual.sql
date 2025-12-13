-- Phase 1: AI Assistant schema catalog and semantic rules
-- Manual migration SQL (40c5b8d791ec)
-- Run this if alembic upgrade head hangs

BEGIN;

-- 1. ai_schema_tables - Database schema catalog
CREATE TABLE IF NOT EXISTS ai_schema_tables (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schema_name TEXT NOT NULL DEFAULT 'public',
    table_name TEXT NOT NULL,
    human_title TEXT,
    human_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_schema_tables_schema_table UNIQUE (schema_name, table_name)
);

CREATE INDEX IF NOT EXISTS idx_ai_schema_tables_active ON ai_schema_tables (is_active);

-- 2. ai_schema_columns - Column metadata  
CREATE TABLE IF NOT EXISTS ai_schema_columns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    table_id UUID NOT NULL REFERENCES ai_schema_tables(id) ON DELETE CASCADE,
    column_name TEXT NOT NULL,
    data_type TEXT,
    is_nullable BOOLEAN,
    human_title TEXT,
    human_description TEXT,
    example_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_schema_columns_table_column UNIQUE (table_id, column_name)
);

CREATE INDEX IF NOT EXISTS idx_ai_schema_columns_table_id ON ai_schema_columns (table_id);

-- 3. ai_semantic_rules - User intent patterns
CREATE TABLE IF NOT EXISTS ai_semantic_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    locale TEXT NOT NULL DEFAULT 'ru-RU',
    domain TEXT NOT NULL DEFAULT 'analytics',
    user_pattern TEXT NOT NULL,
    normalized_intent TEXT,
    target_description TEXT,
    target_sql_template TEXT,
    target_action_type TEXT NOT NULL DEFAULT 'GENERATE_SQL',
    confidence NUMERIC(3,2),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_semantic_rules_domain_locale ON ai_semantic_rules (domain, locale);
CREATE INDEX IF NOT EXISTS idx_ai_semantic_rules_active ON ai_semantic_rules (is_active);

-- 4. Extend ai_query_log → ai_queries_log
-- Check if rename needed
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_query_log') THEN
        ALTER TABLE ai_query_log RENAME TO ai_queries_log;
    END IF;
END $$;

-- Add new columns if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'domain') THEN
        ALTER TABLE ai_queries_log ADD COLUMN domain TEXT DEFAULT 'analytics';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'input_locale') THEN
        ALTER TABLE ai_queries_log ADD COLUMN input_locale TEXT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'context') THEN
        ALTER TABLE ai_queries_log ADD COLUMN context JSONB;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'used_semantic_rule_id') THEN
        ALTER TABLE ai_queries_log ADD COLUMN used_semantic_rule_id UUID REFERENCES ai_semantic_rules(id) ON DELETE SET NULL;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'execution_ok') THEN
        ALTER TABLE ai_queries_log ADD COLUMN execution_ok BOOLEAN;
    END IF;
    
   IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'execution_result_meta') THEN
        ALTER TABLE ai_queries_log ADD COLUMN execution_result_meta JSONB;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ai_queries_log' AND column_name = 'ai_answer_preview') THEN
        ALTER TABLE ai_queries_log ADD COLUMN ai_answer_preview TEXT;
    END IF;
END $$;

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_ai_queries_log_domain ON ai_queries_log (domain);
CREATE INDEX IF NOT EXISTS idx_ai_queries_log_semantic_rule ON ai_queries_log (used_semantic_rule_id);

-- Update alembic version
INSERT INTO alembic_version (version_num) VALUES ('40c5b8d791ec')
ON CONFLICT (version_num) DO NOTHING;

COMMIT;

-- Verify tables created
SELECT tablename FROM pg_tables 
WHERE schema name = 'public' AND tablename LIKE 'ai_%'
ORDER BY tablename;
