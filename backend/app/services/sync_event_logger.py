"""
Sync Event Logger Service for real-time streaming of sync operation logs
"""
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from app.models_sqlalchemy.models import SyncEventLog
from app.models_sqlalchemy import SessionLocal
from app.utils.logger import logger
import asyncio
import json

# In-memory cancellation flags (fast lookup)
_cancelled_run_ids: set = set()


class SyncEventLogger:
    """
    Service for logging sync events with real-time streaming support.
    Emits structured log events that can be streamed via SSE and persisted to database.
    """
    
    def __init__(self, user_id: str, sync_type: str, run_id: Optional[str] = None):
        self.user_id = user_id
        self.sync_type = sync_type
        self.run_id = run_id or f"{sync_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.db: Optional[Session] = None
        self.events = []
        
    def _get_db(self) -> Session:
        """Get or create database session"""
        if self.db is None:
            self.db = SessionLocal()
        return self.db
    
    def _persist_event(self, event: Dict[str, Any]):
        """Persist event to database"""
        try:
            db = self._get_db()
            event_log = SyncEventLog(
                run_id=self.run_id,
                user_id=self.user_id,
                sync_type=self.sync_type,
                event_type=event.get('event_type', 'log'),
                level=event.get('level', 'info'),
                message=event.get('message', ''),
                http_method=event.get('http_method'),
                http_url=event.get('http_url'),
                http_status=event.get('http_status'),
                http_duration_ms=event.get('http_duration_ms'),
                current_page=event.get('current_page'),
                total_pages=event.get('total_pages'),
                items_fetched=event.get('items_fetched'),
                items_stored=event.get('items_stored'),
                progress_pct=event.get('progress_pct'),
                extra_data=event.get('extra_data'),
                timestamp=datetime.utcnow()
            )
            db.add(event_log)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to persist sync event: {str(e)}")
            if self.db:
                self.db.rollback()
    
    def emit_event(self, event: Dict[str, Any]):
        """Emit a log event (stores in memory and persists to DB)"""
        event['run_id'] = self.run_id
        event['timestamp'] = datetime.utcnow().isoformat()
        self.events.append(event)
        self._persist_event(event)
        logger.info(f"[{self.run_id}] {event.get('message', '')}")
    
    def log_start(self, message: str):
        """Log sync start event"""
        self.emit_event({
            'event_type': 'start',
            'level': 'info',
            'message': message
        })
    
    def log_progress(self, message: str, current_page: int, total_pages: Optional[int], 
                    items_fetched: int, items_stored: int):
        """Log progress event with pagination details"""
        progress_pct = None
        if total_pages and total_pages > 0:
            progress_pct = (current_page / total_pages) * 100
        
        self.emit_event({
            'event_type': 'progress',
            'level': 'info',
            'message': message,
            'current_page': current_page,
            'total_pages': total_pages,
            'items_fetched': items_fetched,
            'items_stored': items_stored,
            'progress_pct': progress_pct
        })
    
    def log_http_request(self, method: str, url: str, status: int, duration_ms: int, 
                        items_count: Optional[int] = None):
        """Log HTTP request/response details"""
        message = f"{method} {url} → {status} ({duration_ms}ms)"
        if items_count is not None:
            message += f" | {items_count} items"
        
        self.emit_event({
            'event_type': 'http',
            'level': 'info',
            'message': message,
            'http_method': method,
            'http_url': url,
            'http_status': status,
            'http_duration_ms': duration_ms,
            'extra_data': {'items_count': items_count} if items_count is not None else None
        })
    
    def log_info(self, message: str, extra_data: Optional[Dict[str, Any]] = None):
        """Log info message"""
        self.emit_event({
            'event_type': 'log',
            'level': 'info',
            'message': message,
            'extra_data': extra_data
        })
    
    def log_warning(self, message: str, extra_data: Optional[Dict[str, Any]] = None):
        """Log warning message"""
        self.emit_event({
            'event_type': 'log',
            'level': 'warning',
            'message': message,
            'extra_data': extra_data
        })
    
    def log_error(self, message: str, error: Optional[Exception] = None, 
                 extra_data: Optional[Dict[str, Any]] = None):
        """Log error message"""
        error_data = extra_data or {}
        if error:
            error_data['error_type'] = type(error).__name__
            error_data['error_message'] = str(error)
        
        self.emit_event({
            'event_type': 'error',
            'level': 'error',
            'message': message,
            'extra_data': error_data
        })
    
    def log_done(self, message: str, total_fetched: int, total_stored: int, duration_ms: int):
        """Log completion event"""
        self.emit_event({
            'event_type': 'done',
            'level': 'info',
            'message': message,
            'items_fetched': total_fetched,
            'items_stored': total_stored,
            'extra_data': {'duration_ms': duration_ms}
        })
    
    def close(self):
        """Close database session"""
        if self.db:
            self.db.close()
            self.db = None
    
    async def stream_events(self) -> AsyncGenerator[str, None]:
        """
        Stream events as Server-Sent Events (SSE) format.
        Yields events as they are emitted.
        """
        last_index = 0
        
        while True:
            if last_index < len(self.events):
                for event in self.events[last_index:]:
                    yield f"event: {event['event_type']}\n"
                    yield f"data: {json.dumps(event)}\n\n"
                    last_index += 1
            
            if self.events and self.events[-1].get('event_type') == 'done':
                break
            
            await asyncio.sleep(0.1)


def is_cancelled(run_id: str) -> bool:
    """Check if a sync run has been cancelled"""
    if run_id in _cancelled_run_ids:
        return True
    # Also check database for persistence
    db = SessionLocal()
    try:
        cancelled_event = db.query(SyncEventLog).filter(
            SyncEventLog.run_id == run_id,
            SyncEventLog.event_type == 'cancelled'
        ).first()
        if cancelled_event:
            _cancelled_run_ids.add(run_id)
            return True
        return False
    finally:
        db.close()


def cancel_sync(run_id: str, user_id: str) -> bool:
    """Mark a sync run as cancelled"""
    _cancelled_run_ids.add(run_id)
    # Also persist to database
    db = SessionLocal()
    try:
        # Check if already cancelled
        existing = db.query(SyncEventLog).filter(
            SyncEventLog.run_id == run_id,
            SyncEventLog.event_type == 'cancelled'
        ).first()
        if existing:
            return True
        
        # Get sync_type from existing events
        first_event = db.query(SyncEventLog).filter(
            SyncEventLog.run_id == run_id
        ).first()
        sync_type = first_event.sync_type if first_event else 'unknown'
        
        # Create cancellation event
        cancel_event = SyncEventLog(
            run_id=run_id,
            user_id=user_id,
            sync_type=sync_type,
            event_type='cancelled',
            level='warning',
            message='Sync operation cancelled by user',
            timestamp=datetime.utcnow()
        )
        db.add(cancel_event)
        db.commit()
        logger.info(f"Marked sync run {run_id} as cancelled")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel sync {run_id}: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()


def get_sync_events_from_db(run_id: str, user_id: str) -> list:
    """Retrieve all sync events for a given run_id from database"""
    db = SessionLocal()
    try:
        events = db.query(SyncEventLog).filter(
            SyncEventLog.run_id == run_id,
            SyncEventLog.user_id == user_id
        ).order_by(SyncEventLog.timestamp).all()
        
        return [{
            'run_id': e.run_id,
            'event_type': e.event_type,
            'level': e.level,
            'message': e.message,
            'http_method': e.http_method,
            'http_url': e.http_url,
            'http_status': e.http_status,
            'http_duration_ms': e.http_duration_ms,
            'current_page': e.current_page,
            'total_pages': e.total_pages,
            'items_fetched': e.items_fetched,
            'items_stored': e.items_stored,
            'progress_pct': e.progress_pct,
            'extra_data': e.extra_data,
            'timestamp': e.timestamp.isoformat()
        } for e in events]
    finally:
        db.close()
