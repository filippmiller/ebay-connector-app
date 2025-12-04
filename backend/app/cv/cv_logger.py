"""
Structured Logging System for CV Module

Uses loguru for structured logging with support for:
- Console output with colors
- File logging
- Supabase logging
- WebSocket broadcasting for live debug console
"""

import sys
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque
import threading

from loguru import logger

from .config import cv_settings, SUBSYSTEMS


class LogLevel(str, Enum):
    """Log levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warn"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: str
    level: str
    subsystem: str
    message: str
    payload: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "subsystem": self.subsystem,
            "message": self.message,
            "payload": self.payload or {},
        }


class CVLogger:
    """
    Centralized logging system for CV module
    
    Features:
    - Structured logging with subsystem tags
    - Log buffering for batch Supabase writes
    - WebSocket broadcasting for live console
    - Metrics tracking (FPS, errors, etc.)
    """
    
    _instance: Optional["CVLogger"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "CVLogger":
        """Singleton pattern for global logger access"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._log_buffer: deque = deque(maxlen=cv_settings.log_buffer_size)
        self._ws_callbacks: List[Callable] = []
        self._metrics: Dict[str, Any] = {
            "fps": 0,
            "frames_processed": 0,
            "ocr_count": 0,
            "errors": 0,
            "last_error": None,
            "camera_status": "disconnected",
            "cv_status": "stopped",
            "ocr_status": "stopped",
            "supabase_status": "disconnected",
        }
        self._supabase_writer = None
        
        # Configure loguru
        self._configure_logger()
    
    def _configure_logger(self):
        """Configure loguru with custom format"""
        # Remove default handler
        logger.remove()
        
        # Add console handler with colors
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>[{extra[subsystem]}]</cyan> | "
            "<level>{message}</level>"
        )
        
        logger.add(
            sys.stdout,
            format=log_format,
            level=cv_settings.log_level,
            colorize=True,
        )
        
        # Add file handler for errors
        logger.add(
            "logs/cv_errors.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | [{extra[subsystem]}] | {message}",
            level="ERROR",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
        )
    
    def set_supabase_writer(self, writer):
        """Set Supabase writer for log persistence"""
        self._supabase_writer = writer
    
    def register_ws_callback(self, callback: Callable):
        """Register callback for WebSocket broadcasting"""
        self._ws_callbacks.append(callback)
    
    def unregister_ws_callback(self, callback: Callable):
        """Unregister WebSocket callback"""
        if callback in self._ws_callbacks:
            self._ws_callbacks.remove(callback)
    
    def _create_entry(
        self, 
        level: LogLevel, 
        subsystem: str, 
        message: str, 
        payload: Optional[Dict] = None
    ) -> LogEntry:
        """Create a structured log entry"""
        return LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level.value,
            subsystem=subsystem,
            message=message,
            payload=payload,
        )
    
    async def _broadcast_to_ws(self, entry: LogEntry):
        """Broadcast log entry to all WebSocket clients"""
        entry_dict = entry.to_dict()
        for callback in self._ws_callbacks:
            try:
                await callback(entry_dict)
            except Exception:
                pass  # Ignore callback errors
    
    async def _persist_to_supabase(self, entry: LogEntry):
        """Persist log entry to Supabase"""
        if self._supabase_writer and cv_settings.log_to_supabase:
            try:
                await self._supabase_writer.write_log(entry.to_dict())
            except Exception as e:
                # Log locally but don't create infinite loop
                logger.bind(subsystem=SUBSYSTEMS["error"]).error(
                    f"Failed to persist log to Supabase: {e}"
                )
    
    def _log(
        self, 
        level: LogLevel, 
        subsystem: str, 
        message: str, 
        payload: Optional[Dict] = None,
        persist: bool = True
    ):
        """Internal logging method"""
        entry = self._create_entry(level, subsystem, message, payload)
        
        # Add to buffer
        self._log_buffer.append(entry)
        
        # Log with loguru
        log_func = getattr(logger.bind(subsystem=subsystem), level.value)
        if payload:
            log_func(f"{message} | {json.dumps(payload)}")
        else:
            log_func(message)
        
        # Update error metrics
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            self._metrics["errors"] += 1
            self._metrics["last_error"] = {
                "message": message,
                "timestamp": entry.timestamp,
                "subsystem": subsystem,
            }
        
        # Async operations (broadcast and persist)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_to_ws(entry))
            if persist:
                loop.create_task(self._persist_to_supabase(entry))
        except RuntimeError:
            # No running event loop, skip async operations
            pass
    
    # Convenience methods for each subsystem
    def camera(self, message: str, level: LogLevel = LogLevel.INFO, payload: Optional[Dict] = None):
        """Log camera-related message"""
        self._log(level, SUBSYSTEMS["camera"], message, payload)
    
    def stream(self, message: str, level: LogLevel = LogLevel.INFO, payload: Optional[Dict] = None):
        """Log stream-related message"""
        self._log(level, SUBSYSTEMS["stream"], message, payload)
    
    def cv(self, message: str, level: LogLevel = LogLevel.INFO, payload: Optional[Dict] = None):
        """Log CV-related message"""
        self._log(level, SUBSYSTEMS["cv"], message, payload)
    
    def ocr(self, message: str, level: LogLevel = LogLevel.INFO, payload: Optional[Dict] = None):
        """Log OCR-related message"""
        self._log(level, SUBSYSTEMS["ocr"], message, payload)
    
    def supabase(self, message: str, level: LogLevel = LogLevel.INFO, payload: Optional[Dict] = None):
        """Log Supabase-related message"""
        self._log(level, SUBSYSTEMS["supabase"], message, payload, persist=False)
    
    def error(self, message: str, subsystem: str = "ERROR", payload: Optional[Dict] = None):
        """Log error message"""
        self._log(LogLevel.ERROR, subsystem, message, payload)
    
    def system(self, message: str, level: LogLevel = LogLevel.INFO, payload: Optional[Dict] = None):
        """Log system-level message"""
        self._log(level, SUBSYSTEMS["system"], message, payload)
    
    # Metrics methods
    def update_fps(self, fps: float):
        """Update FPS metric"""
        self._metrics["fps"] = round(fps, 1)
    
    def increment_frames(self):
        """Increment processed frames counter"""
        self._metrics["frames_processed"] += 1
    
    def increment_ocr(self):
        """Increment OCR count"""
        self._metrics["ocr_count"] += 1
    
    def set_status(self, component: str, status: str):
        """Set component status"""
        key = f"{component}_status"
        if key in self._metrics:
            self._metrics[key] = status
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return self._metrics.copy()
    
    def get_recent_logs(self, count: int = 50) -> List[Dict]:
        """Get recent log entries"""
        logs = list(self._log_buffer)[-count:]
        return [log.to_dict() for log in logs]


# Global logger instance
cv_logger = CVLogger()

