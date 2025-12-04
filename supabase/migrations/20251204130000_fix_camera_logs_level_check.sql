-- Fix camera_logs level check constraint to use 'warning' instead of 'warn'
-- This matches loguru's log level naming

-- Drop the old constraint
ALTER TABLE camera_logs DROP CONSTRAINT IF EXISTS camera_logs_level_check;

-- Add the new constraint with 'warning'
ALTER TABLE camera_logs ADD CONSTRAINT camera_logs_level_check 
    CHECK (level IN ('debug', 'info', 'warning', 'warn', 'error', 'critical'));

-- Update any existing 'warn' entries to 'warning' (optional, for consistency)
UPDATE camera_logs SET level = 'warning' WHERE level = 'warn';

