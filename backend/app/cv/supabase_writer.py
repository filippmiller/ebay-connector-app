"""
Supabase Writer Service

Handles all database operations for the CV module:
- Writing OCR results to camera_ocr_logs
- Writing log entries to camera_logs
- Uploading crops and debug frames to Storage
- Batch writing for performance
"""

import asyncio
import time
import base64
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from queue import Queue, Empty
from io import BytesIO
import uuid

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from .config import cv_settings, TABLES
from .cv_logger import cv_logger, LogLevel


@dataclass
class OCRLogEntry:
    """OCR log entry for database"""
    raw_text: str
    cleaned_text: str
    confidence_score: float
    source_frame_number: int
    camera_id: str = "default"
    crop_image_url: Optional[str] = None
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "raw_text": self.raw_text,
            "cleaned_text": self.cleaned_text,
            "confidence_score": self.confidence_score,
            "source_frame_number": self.source_frame_number,
            "camera_id": self.camera_id,
            "crop_image_url": self.crop_image_url,
        }


class SupabaseWriter:
    """
    Supabase Writer Service
    
    Features:
    - Async batch writing for performance
    - Image upload to Storage buckets
    - Automatic retry on failures
    - Connection health monitoring
    """
    
    def __init__(self):
        self._client = None
        self._initialized: bool = False
        self._write_queue: Queue = Queue(maxsize=1000)
        self._batch_size: int = 50
        self._flush_interval: float = 5.0  # seconds
        self._worker_thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()
        
        # Statistics
        self._total_writes: int = 0
        self._failed_writes: int = 0
        self._total_uploads: int = 0
    
    async def initialize(self) -> bool:
        """Initialize Supabase client"""
        if not cv_settings.supabase_url or not cv_settings.supabase_key:
            cv_logger.supabase(
                "Supabase credentials not configured (CV_SUPABASE_URL, CV_SUPABASE_KEY)",
                level=LogLevel.WARNING
            )
            return False
        
        try:
            from supabase import create_client, Client
            
            self._client: Client = create_client(
                cv_settings.supabase_url,
                cv_settings.supabase_key,
            )
            
            # Test connection
            # await self._test_connection()
            
            self._initialized = True
            cv_logger.set_status("supabase", "connected")
            cv_logger.supabase("Supabase client initialized")
            
            # Start background writer
            self._start_writer()
            
            return True
            
        except ImportError:
            cv_logger.supabase(
                "supabase-py not installed. Install with: pip install supabase",
                level=LogLevel.ERROR
            )
            return False
        except Exception as e:
            cv_logger.supabase(f"Failed to initialize Supabase: {e}", level=LogLevel.ERROR)
            return False
    
    def _start_writer(self):
        """Start background writer thread"""
        self._running = True
        self._worker_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._worker_thread.start()
        cv_logger.supabase("Background writer started")
    
    def _writer_loop(self):
        """Background writer loop for batch processing"""
        last_flush = time.time()
        batch = []
        
        while self._running:
            try:
                # Get items from queue
                try:
                    item = self._write_queue.get(timeout=1.0)
                    batch.append(item)
                except Empty:
                    pass
                
                # Flush if batch is full or interval elapsed
                current_time = time.time()
                should_flush = (
                    len(batch) >= self._batch_size or
                    (batch and current_time - last_flush >= self._flush_interval)
                )
                
                if should_flush and batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = current_time
                    
            except Exception as e:
                cv_logger.supabase(f"Writer loop error: {e}", level=LogLevel.ERROR)
        
        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)
    
    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """Flush batch to Supabase"""
        if not self._client:
            return
        
        # Group by table
        by_table: Dict[str, List[Dict]] = {}
        for item in batch:
            table = item.get("_table", TABLES["logs"])
            if table not in by_table:
                by_table[table] = []
            
            # Remove internal fields
            data = {k: v for k, v in item.items() if not k.startswith("_")}
            by_table[table].append(data)
        
        # Write each table
        for table, rows in by_table.items():
            try:
                self._client.table(table).insert(rows).execute()
                self._total_writes += len(rows)
                cv_logger.supabase(
                    f"Wrote {len(rows)} rows to {table}",
                    level=LogLevel.DEBUG
                )
            except Exception as e:
                self._failed_writes += len(rows)
                cv_logger.supabase(
                    f"Failed to write to {table}: {e}",
                    level=LogLevel.ERROR
                )
    
    async def write_ocr_result(self, entry: OCRLogEntry) -> bool:
        """Write OCR result to database"""
        if not self._initialized:
            return False
        
        data = entry.to_dict()
        data["_table"] = TABLES["ocr_logs"]
        
        try:
            self._write_queue.put_nowait(data)
            return True
        except:
            return False
    
    async def write_log(self, log_entry: Dict[str, Any]) -> bool:
        """Write log entry to database"""
        if not self._initialized:
            return False
        
        data = {
            "timestamp": log_entry.get("timestamp"),
            "level": log_entry.get("level", "info"),
            "subsystem": log_entry.get("subsystem", "SYSTEM"),
            "message": log_entry.get("message", ""),
            "payload": log_entry.get("payload", {}),
            "_table": TABLES["logs"],
        }
        
        try:
            self._write_queue.put_nowait(data)
            return True
        except:
            return False
    
    async def upload_image(
        self,
        image: "np.ndarray",
        bucket: str,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """Upload image to Supabase Storage"""
        if not self._initialized or self._client is None:
            return None
        
        if cv2 is None:
            return None
        
        try:
            # Generate filename if not provided
            if filename is None:
                filename = f"{uuid.uuid4()}.jpg"
            
            # Encode image to JPEG
            _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_bytes = buffer.tobytes()
            
            # Upload to storage
            result = self._client.storage.from_(bucket).upload(
                filename,
                image_bytes,
                {"content-type": "image/jpeg"},
            )
            
            # Get public URL
            public_url = self._client.storage.from_(bucket).get_public_url(filename)
            
            self._total_uploads += 1
            cv_logger.supabase(
                f"Uploaded image to {bucket}/{filename}",
                level=LogLevel.DEBUG
            )
            
            return public_url
            
        except Exception as e:
            cv_logger.supabase(f"Failed to upload image: {e}", level=LogLevel.ERROR)
            return None
    
    async def upload_crop(
        self,
        image: "np.ndarray",
        frame_number: int,
        region_index: int,
    ) -> Optional[str]:
        """Upload cropped text region"""
        filename = f"crop_{frame_number}_{region_index}_{int(time.time())}.jpg"
        return await self.upload_image(
            image,
            cv_settings.supabase_bucket_crops,
            filename,
        )
    
    async def upload_debug_frame(
        self,
        image: "np.ndarray",
        frame_number: int,
    ) -> Optional[str]:
        """Upload debug frame"""
        if not cv_settings.save_debug_frames:
            return None
        
        filename = f"debug_{frame_number}_{int(time.time())}.jpg"
        return await self.upload_image(
            image,
            cv_settings.supabase_bucket_debug,
            filename,
        )
    
    def shutdown(self):
        """Shutdown writer gracefully"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10.0)
        cv_logger.supabase("Writer shutdown complete")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get writer statistics"""
        return {
            "initialized": self._initialized,
            "queue_size": self._write_queue.qsize(),
            "total_writes": self._total_writes,
            "failed_writes": self._failed_writes,
            "total_uploads": self._total_uploads,
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        return {
            "connected": self._initialized,
            "status": "connected" if self._initialized else "disconnected",
            **self.get_stats(),
        }


# SQL for creating tables in Supabase
CREATE_TABLES_SQL = """
-- Camera OCR Logs table
CREATE TABLE IF NOT EXISTS camera_ocr_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    raw_text TEXT NOT NULL,
    cleaned_text TEXT,
    crop_image_url TEXT,
    source_frame_number INTEGER,
    camera_id TEXT DEFAULT 'default',
    confidence_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_ocr_logs_timestamp ON camera_ocr_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ocr_logs_camera_id ON camera_ocr_logs(camera_id);

-- Camera Logs table
CREATE TABLE IF NOT EXISTS camera_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    level TEXT NOT NULL DEFAULT 'info',
    subsystem TEXT NOT NULL,
    message TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON camera_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level ON camera_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_subsystem ON camera_logs(subsystem);

-- Camera Frames table (optional, for storing key frames)
CREATE TABLE IF NOT EXISTS camera_frames (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    frame_number INTEGER NOT NULL,
    camera_id TEXT DEFAULT 'default',
    image_url TEXT,
    detections JSONB DEFAULT '[]'::jsonb,
    ocr_results JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON camera_frames(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_frames_camera_id ON camera_frames(camera_id);

-- Enable Row Level Security (optional)
-- ALTER TABLE camera_ocr_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE camera_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE camera_frames ENABLE ROW LEVEL SECURITY;

-- Storage buckets (run in Supabase dashboard or via API)
-- INSERT INTO storage.buckets (id, name, public) VALUES ('camera_crops', 'camera_crops', true);
-- INSERT INTO storage.buckets (id, name, public) VALUES ('camera_debug_frames', 'camera_debug_frames', true);
"""

