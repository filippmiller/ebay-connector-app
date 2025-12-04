-- CV Module Database Schema Migration
-- Created: 2024-12-04
-- Description: Tables for Computer Vision module with DJI Osmo Pocket 3 integration

-- ============================================
-- Camera OCR Logs Table
-- Stores all OCR recognition results
-- ============================================
CREATE TABLE IF NOT EXISTS camera_ocr_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT,
    crop_image_url TEXT,
    source_frame_number INTEGER,
    camera_id TEXT DEFAULT 'default',
    confidence_score FLOAT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_camera_ocr_logs_timestamp ON camera_ocr_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_camera_ocr_logs_camera_id ON camera_ocr_logs(camera_id);
CREATE INDEX IF NOT EXISTS idx_camera_ocr_logs_confidence ON camera_ocr_logs(confidence_score);

-- Enable full-text search on raw_text
CREATE INDEX IF NOT EXISTS idx_camera_ocr_logs_text_search ON camera_ocr_logs USING gin(to_tsvector('english', raw_text));

COMMENT ON TABLE camera_ocr_logs IS 'Stores OCR recognition results from computer vision pipeline';
COMMENT ON COLUMN camera_ocr_logs.raw_text IS 'Raw text recognized by OCR engine';
COMMENT ON COLUMN camera_ocr_logs.cleaned_text IS 'Cleaned and normalized text';
COMMENT ON COLUMN camera_ocr_logs.crop_image_url IS 'URL to cropped image region in storage';
COMMENT ON COLUMN camera_ocr_logs.source_frame_number IS 'Frame number from video stream';
COMMENT ON COLUMN camera_ocr_logs.confidence_score IS 'OCR confidence score (0-1)';


-- ============================================
-- Camera Logs Table
-- Stores all system logs from CV module
-- ============================================
CREATE TABLE IF NOT EXISTS camera_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    level TEXT NOT NULL DEFAULT 'info' CHECK (level IN ('debug', 'info', 'warn', 'error', 'critical')),
    subsystem TEXT NOT NULL CHECK (subsystem IN ('CAMERA', 'STREAM', 'CV', 'OCR', 'SUPABASE', 'ERROR', 'SYSTEM')),
    message TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for log queries
CREATE INDEX IF NOT EXISTS idx_camera_logs_timestamp ON camera_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_camera_logs_level ON camera_logs(level);
CREATE INDEX IF NOT EXISTS idx_camera_logs_subsystem ON camera_logs(subsystem);
CREATE INDEX IF NOT EXISTS idx_camera_logs_level_timestamp ON camera_logs(level, timestamp DESC);

COMMENT ON TABLE camera_logs IS 'System logs from CV module components';
COMMENT ON COLUMN camera_logs.level IS 'Log level: debug, info, warn, error, critical';
COMMENT ON COLUMN camera_logs.subsystem IS 'Component that generated the log';
COMMENT ON COLUMN camera_logs.payload IS 'Additional structured data in JSON format';


-- ============================================
-- Camera Frames Table (Optional)
-- Stores key frames with detection data
-- ============================================
CREATE TABLE IF NOT EXISTS camera_frames (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    frame_number INTEGER NOT NULL,
    camera_id TEXT DEFAULT 'default',
    image_url TEXT,
    width INTEGER,
    height INTEGER,
    detections JSONB DEFAULT '[]'::jsonb,
    ocr_results JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    processing_time_ms FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_camera_frames_timestamp ON camera_frames(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_camera_frames_camera_id ON camera_frames(camera_id);
CREATE INDEX IF NOT EXISTS idx_camera_frames_frame_number ON camera_frames(frame_number);

COMMENT ON TABLE camera_frames IS 'Key frames with detection and OCR data';
COMMENT ON COLUMN camera_frames.detections IS 'Array of detected objects with bounding boxes';
COMMENT ON COLUMN camera_frames.ocr_results IS 'Array of OCR results for the frame';


-- ============================================
-- Camera Sessions Table
-- Tracks camera connection sessions
-- ============================================
CREATE TABLE IF NOT EXISTS camera_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id TEXT NOT NULL DEFAULT 'default',
    started_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'ended', 'error')),
    total_frames INTEGER DEFAULT 0,
    total_detections INTEGER DEFAULT 0,
    total_ocr_results INTEGER DEFAULT 0,
    avg_fps FLOAT,
    error_message TEXT,
    config JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_camera_sessions_camera_id ON camera_sessions(camera_id);
CREATE INDEX IF NOT EXISTS idx_camera_sessions_status ON camera_sessions(status);
CREATE INDEX IF NOT EXISTS idx_camera_sessions_started_at ON camera_sessions(started_at DESC);

COMMENT ON TABLE camera_sessions IS 'Camera connection session history';


-- ============================================
-- CV Detection Classes Table
-- Configurable detection class settings
-- ============================================
CREATE TABLE IF NOT EXISTS cv_detection_classes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    class_id INTEGER NOT NULL UNIQUE,
    class_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    min_confidence FLOAT DEFAULT 0.5,
    color TEXT DEFAULT '#00FF00',
    alert_on_detection BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pre-populate with COCO classes (subset)
INSERT INTO cv_detection_classes (class_id, class_name, enabled, min_confidence) VALUES
    (0, 'person', true, 0.5),
    (1, 'bicycle', true, 0.5),
    (2, 'car', true, 0.5),
    (3, 'motorcycle', true, 0.5),
    (4, 'airplane', true, 0.5),
    (5, 'bus', true, 0.5),
    (6, 'train', true, 0.5),
    (7, 'truck', true, 0.5),
    (24, 'backpack', true, 0.5),
    (26, 'handbag', true, 0.5),
    (27, 'tie', true, 0.5),
    (28, 'suitcase', true, 0.5),
    (39, 'bottle', true, 0.5),
    (41, 'cup', true, 0.5),
    (56, 'chair', true, 0.5),
    (63, 'laptop', true, 0.5),
    (64, 'mouse', true, 0.5),
    (65, 'remote', true, 0.5),
    (66, 'keyboard', true, 0.5),
    (67, 'cell phone', true, 0.5),
    (73, 'book', true, 0.5)
ON CONFLICT (class_id) DO NOTHING;

COMMENT ON TABLE cv_detection_classes IS 'YOLO detection class configuration';


-- ============================================
-- Storage Buckets (via SQL)
-- Note: May need to create via Supabase Dashboard
-- ============================================
-- These are typically created via Supabase Dashboard or API
-- but we document them here for reference:

-- Bucket: camera_crops
-- Purpose: Store cropped text regions for OCR
-- Public: true (for easy access)

-- Bucket: camera_debug_frames  
-- Purpose: Store debug frames with annotations
-- Public: false (internal use)


-- ============================================
-- Row Level Security Policies (Optional)
-- Uncomment to enable RLS
-- ============================================

-- ALTER TABLE camera_ocr_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE camera_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE camera_frames ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE camera_sessions ENABLE ROW LEVEL SECURITY;

-- Example policy: Allow all authenticated users to read
-- CREATE POLICY "Allow authenticated read" ON camera_ocr_logs
--     FOR SELECT TO authenticated USING (true);

-- Example policy: Allow service role full access
-- CREATE POLICY "Service role full access" ON camera_ocr_logs
--     FOR ALL TO service_role USING (true);


-- ============================================
-- Functions for analytics
-- ============================================

-- Function to get OCR stats by time period
CREATE OR REPLACE FUNCTION get_ocr_stats(
    start_time TIMESTAMPTZ DEFAULT NOW() - INTERVAL '24 hours',
    end_time TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
    total_results BIGINT,
    avg_confidence FLOAT,
    unique_texts BIGINT,
    results_per_hour FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as total_results,
        AVG(confidence_score)::FLOAT as avg_confidence,
        COUNT(DISTINCT cleaned_text)::BIGINT as unique_texts,
        (COUNT(*)::FLOAT / GREATEST(EXTRACT(EPOCH FROM (end_time - start_time)) / 3600, 1)) as results_per_hour
    FROM camera_ocr_logs
    WHERE timestamp BETWEEN start_time AND end_time;
END;
$$ LANGUAGE plpgsql;

-- Function to get log stats
CREATE OR REPLACE FUNCTION get_log_stats(
    start_time TIMESTAMPTZ DEFAULT NOW() - INTERVAL '24 hours'
)
RETURNS TABLE (
    subsystem TEXT,
    level TEXT,
    count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cl.subsystem,
        cl.level,
        COUNT(*)::BIGINT as count
    FROM camera_logs cl
    WHERE cl.timestamp >= start_time
    GROUP BY cl.subsystem, cl.level
    ORDER BY count DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to clean old logs (for maintenance)
CREATE OR REPLACE FUNCTION cleanup_old_logs(
    days_to_keep INTEGER DEFAULT 30
)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM camera_logs
    WHERE timestamp < NOW() - (days_to_keep || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_ocr_stats IS 'Get OCR statistics for a time period';
COMMENT ON FUNCTION get_log_stats IS 'Get log counts grouped by subsystem and level';
COMMENT ON FUNCTION cleanup_old_logs IS 'Delete logs older than specified days';

