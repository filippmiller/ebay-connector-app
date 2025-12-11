-- Phase 2: AI Training Center tables (FIXED - no users FK)
-- Admin UI for training AI Assistant with voice input

BEGIN;

-- 1. ai_training_sessions - Training sessions
CREATE TABLE IF NOT EXISTS ai_training_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(36), -- No FK constraint (users table may not exist)
    domain TEXT NOT NULL,
    title TEXT,
    notes TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_training_sessions_user 
    ON ai_training_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_ai_training_sessions_domain 
    ON ai_training_sessions (domain);
CREATE INDEX IF NOT EXISTS idx_ai_training_sessions_started 
    ON ai_training_sessions (started_at DESC);

-- 2. ai_training_examples - Individual training examples
CREATE TABLE IF NOT EXISTS ai_training_examples (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES ai_training_sessions(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    input_mode TEXT DEFAULT 'text',
    raw_input_text TEXT,
    raw_model_output JSONB,
    final_approved_output JSONB,
    linked_semantic_rule_id UUID REFERENCES ai_semantic_rules(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(36),  -- No FK constraint
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(36)   -- No FK constraint
);

CREATE INDEX IF NOT EXISTS idx_ai_training_examples_session 
    ON ai_training_examples (session_id);
CREATE INDEX IF NOT EXISTS idx_ai_training_examples_domain 
    ON ai_training_examples (domain);
CREATE INDEX IF NOT EXISTS idx_ai_training_examples_status 
    ON ai_training_examples (status);
CREATE INDEX IF NOT EXISTS idx_ai_training_examples_semantic_rule 
    ON ai_training_examples (linked_semantic_rule_id);

COMMIT;

-- Verify
SELECT 
    'Phase 2 tables created:' as status,
    COUNT(*) as count
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('ai_training_sessions', 'ai_training_examples');
