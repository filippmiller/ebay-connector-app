-- Vision Brain Layer Database Schema
-- Created: 2024-12-04
-- Description: Tables for AI-powered vision brain system

-- ============================================
-- Vision Sessions Table
-- Tracks vision processing sessions
-- ============================================
CREATE TABLE IF NOT EXISTS vision_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL DEFAULT 'created' 
        CHECK (status IN ('created', 'active', 'paused', 'completed', 'failed', 'cancelled')),
    task_context JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    total_frames INTEGER DEFAULT 0,
    total_detections INTEGER DEFAULT 0,
    total_ocr_results INTEGER DEFAULT 0,
    total_decisions INTEGER DEFAULT 0,
    final_result JSONB,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vision_sessions_status ON vision_sessions(status);
CREATE INDEX IF NOT EXISTS idx_vision_sessions_started_at ON vision_sessions(started_at DESC);

COMMENT ON TABLE vision_sessions IS 'Vision processing sessions with task context and results';


-- ============================================
-- Vision Detections Table
-- YOLO detection results
-- ============================================
CREATE TABLE IF NOT EXISTS vision_detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES vision_sessions(id) ON DELETE CASCADE,
    frame_id INTEGER NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    detector TEXT DEFAULT 'yolo',
    class_name TEXT,
    class_id INTEGER,
    confidence FLOAT,
    bbox JSONB,  -- {x, y, w, h}
    extra JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vision_detections_session ON vision_detections(session_id);
CREATE INDEX IF NOT EXISTS idx_vision_detections_timestamp ON vision_detections(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vision_detections_class ON vision_detections(class_name);
CREATE INDEX IF NOT EXISTS idx_vision_detections_confidence ON vision_detections(confidence);

COMMENT ON TABLE vision_detections IS 'YOLO object detection results per frame';


-- ============================================
-- Vision OCR Results Table
-- OCR text recognition results
-- ============================================
CREATE TABLE IF NOT EXISTS vision_ocr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES vision_sessions(id) ON DELETE CASCADE,
    frame_id INTEGER NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    crop_bbox JSONB,  -- {x, y, w, h}
    raw_text TEXT,
    cleaned_text TEXT,
    confidence FLOAT,
    source_detection_id UUID REFERENCES vision_detections(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vision_ocr_session ON vision_ocr_results(session_id);
CREATE INDEX IF NOT EXISTS idx_vision_ocr_timestamp ON vision_ocr_results(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vision_ocr_text_search ON vision_ocr_results 
    USING gin(to_tsvector('english', cleaned_text));

COMMENT ON TABLE vision_ocr_results IS 'OCR text recognition results linked to detections';


-- ============================================
-- Vision Brain Decisions Table
-- LLM brain decisions and responses
-- ============================================
CREATE TABLE IF NOT EXISTS vision_brain_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES vision_sessions(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    request_payload JSONB NOT NULL,
    response_payload JSONB NOT NULL,
    decision_type TEXT NOT NULL 
        CHECK (decision_type IN ('next_step', 'final_result', 'clarification_needed', 'error', 'waiting')),
    result_status TEXT DEFAULT 'pending' 
        CHECK (result_status IN ('pending', 'accepted', 'rejected')),
    tokens_used INTEGER DEFAULT 0,
    latency_ms FLOAT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brain_decisions_session ON vision_brain_decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_brain_decisions_timestamp ON vision_brain_decisions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_brain_decisions_type ON vision_brain_decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_brain_decisions_status ON vision_brain_decisions(result_status);

COMMENT ON TABLE vision_brain_decisions IS 'LLM brain decisions with full request/response payloads';


-- ============================================
-- Vision Operator Events Table
-- Operator actions and confirmations
-- ============================================
CREATE TABLE IF NOT EXISTS vision_operator_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES vision_sessions(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    event_type TEXT NOT NULL 
        CHECK (event_type IN (
            'action_confirmed', 'action_rejected', 'manual_input',
            'pause_requested', 'resume_requested', 'cancel_requested', 'comment_added'
        )),
    payload JSONB DEFAULT '{}'::jsonb,
    comment TEXT,
    related_decision_id UUID REFERENCES vision_brain_decisions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operator_events_session ON vision_operator_events(session_id);
CREATE INDEX IF NOT EXISTS idx_operator_events_timestamp ON vision_operator_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_operator_events_type ON vision_operator_events(event_type);

COMMENT ON TABLE vision_operator_events IS 'Operator actions and confirmations in response to brain instructions';


-- ============================================
-- Analytics Functions
-- ============================================

-- Get session summary
CREATE OR REPLACE FUNCTION get_vision_session_summary(p_session_id UUID)
RETURNS TABLE (
    session_id UUID,
    status TEXT,
    duration_seconds FLOAT,
    total_frames INTEGER,
    total_detections INTEGER,
    total_ocr_results INTEGER,
    total_decisions INTEGER,
    accepted_decisions INTEGER,
    rejected_decisions INTEGER,
    operator_events INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id as session_id,
        s.status,
        EXTRACT(EPOCH FROM (COALESCE(s.ended_at, NOW()) - s.started_at))::FLOAT as duration_seconds,
        s.total_frames,
        s.total_detections,
        s.total_ocr_results,
        s.total_decisions,
        (SELECT COUNT(*)::INTEGER FROM vision_brain_decisions d WHERE d.session_id = s.id AND d.result_status = 'accepted'),
        (SELECT COUNT(*)::INTEGER FROM vision_brain_decisions d WHERE d.session_id = s.id AND d.result_status = 'rejected'),
        (SELECT COUNT(*)::INTEGER FROM vision_operator_events e WHERE e.session_id = s.id)
    FROM vision_sessions s
    WHERE s.id = p_session_id;
END;
$$ LANGUAGE plpgsql;

-- Get brain performance stats
CREATE OR REPLACE FUNCTION get_brain_performance_stats(
    p_start_time TIMESTAMPTZ DEFAULT NOW() - INTERVAL '24 hours',
    p_end_time TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
    total_decisions BIGINT,
    avg_latency_ms FLOAT,
    total_tokens BIGINT,
    accepted_rate FLOAT,
    error_rate FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as total_decisions,
        AVG(latency_ms)::FLOAT as avg_latency_ms,
        SUM(tokens_used)::BIGINT as total_tokens,
        (COUNT(*) FILTER (WHERE result_status = 'accepted')::FLOAT / NULLIF(COUNT(*), 0)) as accepted_rate,
        (COUNT(*) FILTER (WHERE decision_type = 'error')::FLOAT / NULLIF(COUNT(*), 0)) as error_rate
    FROM vision_brain_decisions
    WHERE timestamp BETWEEN p_start_time AND p_end_time;
END;
$$ LANGUAGE plpgsql;

-- Get detection class distribution
CREATE OR REPLACE FUNCTION get_detection_class_distribution(p_session_id UUID DEFAULT NULL)
RETURNS TABLE (
    class_name TEXT,
    count BIGINT,
    avg_confidence FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        d.class_name,
        COUNT(*)::BIGINT as count,
        AVG(d.confidence)::FLOAT as avg_confidence
    FROM vision_detections d
    WHERE (p_session_id IS NULL OR d.session_id = p_session_id)
    GROUP BY d.class_name
    ORDER BY count DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_vision_session_summary IS 'Get comprehensive summary of a vision session';
COMMENT ON FUNCTION get_brain_performance_stats IS 'Get brain (LLM) performance statistics';
COMMENT ON FUNCTION get_detection_class_distribution IS 'Get distribution of detected object classes';


-- ============================================
-- Cleanup Function
-- ============================================

CREATE OR REPLACE FUNCTION cleanup_old_vision_data(days_to_keep INTEGER DEFAULT 30)
RETURNS TABLE (
    sessions_deleted INTEGER,
    detections_deleted INTEGER,
    ocr_deleted INTEGER,
    decisions_deleted INTEGER,
    events_deleted INTEGER
) AS $$
DECLARE
    v_sessions INTEGER;
    v_detections INTEGER;
    v_ocr INTEGER;
    v_decisions INTEGER;
    v_events INTEGER;
    v_cutoff TIMESTAMPTZ;
BEGIN
    v_cutoff := NOW() - (days_to_keep || ' days')::INTERVAL;
    
    -- Delete old sessions (cascades to related tables)
    DELETE FROM vision_sessions WHERE ended_at < v_cutoff AND status IN ('completed', 'failed', 'cancelled');
    GET DIAGNOSTICS v_sessions = ROW_COUNT;
    
    -- Return counts
    sessions_deleted := v_sessions;
    detections_deleted := 0;  -- Cascaded
    ocr_deleted := 0;  -- Cascaded
    decisions_deleted := 0;  -- Cascaded
    events_deleted := 0;  -- Cascaded
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_vision_data IS 'Delete old vision data older than specified days';

