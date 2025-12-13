"""
Brain Repository - Supabase persistence for vision brain data

Handles all database operations:
- Vision sessions
- Detections
- OCR results
- Brain decisions
- Operator events
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import threading
from queue import Queue, Empty

from ..cv_logger import cv_logger, LogLevel
from .brain_models import (
    VisionSession,
    VisionDetection,
    VisionOCRResult,
    BrainDecisionRecord,
    OperatorEvent,
    SessionStatus,
)


# Table names
TABLES = {
    "sessions": "vision_sessions",
    "detections": "vision_detections",
    "ocr_results": "vision_ocr_results",
    "decisions": "vision_brain_decisions",
    "operator_events": "vision_operator_events",
}


class BrainRepository:
    """
    Supabase repository for vision brain data
    
    All vision data is persisted here - NO local storage.
    """
    
    def __init__(self):
        self._client = None
        self._initialized = False
        self._write_queue: Queue = Queue(maxsize=1000)
        self._batch_size = 50
        self._flush_interval = 3.0
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Statistics
        self._total_writes = 0
        self._failed_writes = 0
    
    async def initialize(self, supabase_url: str, supabase_key: str) -> bool:
        """Initialize Supabase client"""
        try:
            from supabase import create_client
            
            self._client = create_client(supabase_url, supabase_key)
            self._initialized = True
            
            # Start background writer
            self._start_writer()
            
            cv_logger._log(
                LogLevel.INFO, "BRAIN",
                "Brain repository initialized"
            )
            
            return True
            
        except ImportError:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                "supabase-py not installed"
            )
            return False
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to initialize brain repository: {e}"
            )
            return False
    
    def _start_writer(self):
        """Start background write worker"""
        self._running = True
        self._worker_thread = threading.Thread(target=self._write_loop, daemon=True)
        self._worker_thread.start()
    
    def _write_loop(self):
        """Background write loop"""
        import time
        last_flush = time.time()
        batch: List[Dict] = []
        
        while self._running:
            try:
                try:
                    item = self._write_queue.get(timeout=1.0)
                    batch.append(item)
                except Empty:
                    pass
                
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
                cv_logger._log(
                    LogLevel.ERROR, "BRAIN",
                    f"Write loop error: {e}"
                )
        
        # Final flush
        if batch:
            self._flush_batch(batch)
    
    def _flush_batch(self, batch: List[Dict]):
        """Flush batch to Supabase"""
        if not self._client:
            return
        
        # Group by table
        by_table: Dict[str, List[Dict]] = {}
        for item in batch:
            table = item.pop("_table", None)
            if table:
                if table not in by_table:
                    by_table[table] = []
                by_table[table].append(item)
        
        # Write each table
        for table, rows in by_table.items():
            try:
                self._client.table(table).insert(rows).execute()
                self._total_writes += len(rows)
            except Exception as e:
                self._failed_writes += len(rows)
                cv_logger._log(
                    LogLevel.ERROR, "BRAIN",
                    f"Failed to write to {table}: {e}"
                )
    
    # ==================== Sessions ====================
    
    async def create_session(self, session: VisionSession) -> Optional[str]:
        """Create a new vision session"""
        if not self._client:
            return None
        
        try:
            data = session.to_dict()
            result = self._client.table(TABLES["sessions"]).insert(data).execute()
            
            cv_logger._log(
                LogLevel.INFO, "BRAIN",
                f"Session created: {session.id}"
            )
            
            return session.id
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to create session: {e}"
            )
            return None
    
    async def update_session(
        self, 
        session_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """Update session data"""
        if not self._client:
            return False
        
        try:
            self._client.table(TABLES["sessions"]).update(updates).eq("id", session_id).execute()
            return True
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to update session {session_id}: {e}"
            )
            return False
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID"""
        if not self._client:
            return None
        
        try:
            result = self._client.table(TABLES["sessions"]).select("*").eq("id", session_id).single().execute()
            return result.data
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to get session {session_id}: {e}"
            )
            return None
    
    async def list_sessions(
        self, 
        limit: int = 50, 
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Dict]:
        """List sessions"""
        if not self._client:
            return []
        
        try:
            query = self._client.table(TABLES["sessions"]).select("*")
            
            if status:
                query = query.eq("status", status)
            
            query = query.order("started_at", desc=True).range(offset, offset + limit - 1)
            result = query.execute()
            
            return result.data
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to list sessions: {e}"
            )
            return []
    
    async def end_session(
        self, 
        session_id: str, 
        status: SessionStatus,
        final_result: Optional[Dict] = None
    ) -> bool:
        """End a session"""
        updates = {
            "status": status.value,
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }
        if final_result:
            updates["final_result"] = final_result
        
        return await self.update_session(session_id, updates)
    
    # ==================== Detections ====================
    
    async def save_detection(self, detection: VisionDetection):
        """Save a detection (queued for batch write)"""
        data = detection.to_dict()
        data["_table"] = TABLES["detections"]
        
        try:
            self._write_queue.put_nowait(data)
        except:
            pass
    
    async def save_detections(self, detections: List[VisionDetection]):
        """Save multiple detections"""
        for det in detections:
            await self.save_detection(det)
    
    async def get_session_detections(
        self, 
        session_id: str, 
        limit: int = 100
    ) -> List[Dict]:
        """Get detections for a session"""
        if not self._client:
            return []
        
        try:
            result = (
                self._client.table(TABLES["detections"])
                .select("*")
                .eq("session_id", session_id)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to get detections: {e}"
            )
            return []
    
    # ==================== OCR Results ====================
    
    async def save_ocr_result(self, ocr_result: VisionOCRResult):
        """Save an OCR result (queued for batch write)"""
        data = ocr_result.to_dict()
        data["_table"] = TABLES["ocr_results"]
        
        try:
            self._write_queue.put_nowait(data)
        except:
            pass
    
    async def save_ocr_results(self, ocr_results: List[VisionOCRResult]):
        """Save multiple OCR results"""
        for ocr in ocr_results:
            await self.save_ocr_result(ocr)
    
    async def get_session_ocr_results(
        self, 
        session_id: str, 
        limit: int = 100
    ) -> List[Dict]:
        """Get OCR results for a session"""
        if not self._client:
            return []
        
        try:
            result = (
                self._client.table(TABLES["ocr_results"])
                .select("*")
                .eq("session_id", session_id)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to get OCR results: {e}"
            )
            return []
    
    # ==================== Brain Decisions ====================
    
    async def save_decision(self, decision: BrainDecisionRecord):
        """Save a brain decision (queued for batch write)"""
        data = decision.to_dict()
        data["_table"] = TABLES["decisions"]
        
        try:
            self._write_queue.put_nowait(data)
        except:
            pass
    
    async def update_decision_status(
        self, 
        decision_id: str, 
        status: str
    ) -> bool:
        """Update decision status (accepted/rejected)"""
        if not self._client:
            return False
        
        try:
            self._client.table(TABLES["decisions"]).update(
                {"result_status": status}
            ).eq("id", decision_id).execute()
            return True
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to update decision status: {e}"
            )
            return False
    
    async def get_session_decisions(
        self, 
        session_id: str, 
        limit: int = 50
    ) -> List[Dict]:
        """Get decisions for a session"""
        if not self._client:
            return []
        
        try:
            result = (
                self._client.table(TABLES["decisions"])
                .select("*")
                .eq("session_id", session_id)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to get decisions: {e}"
            )
            return []
    
    # ==================== Operator Events ====================
    
    async def save_operator_event(self, event: OperatorEvent):
        """Save an operator event (queued for batch write)"""
        data = event.to_dict()
        data["_table"] = TABLES["operator_events"]
        
        try:
            self._write_queue.put_nowait(data)
        except:
            pass
    
    async def get_session_operator_events(
        self, 
        session_id: str, 
        limit: int = 100
    ) -> List[Dict]:
        """Get operator events for a session"""
        if not self._client:
            return []
        
        try:
            result = (
                self._client.table(TABLES["operator_events"])
                .select("*")
                .eq("session_id", session_id)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to get operator events: {e}"
            )
            return []
    
    # ==================== Session Details ====================
    
    async def get_session_details(self, session_id: str) -> Dict[str, Any]:
        """Get complete session details including all related data"""
        session = await self.get_session(session_id)
        if not session:
            return {}
        
        detections = await self.get_session_detections(session_id)
        ocr_results = await self.get_session_ocr_results(session_id)
        decisions = await self.get_session_decisions(session_id)
        events = await self.get_session_operator_events(session_id)
        
        return {
            "session": session,
            "detections": detections,
            "ocr_results": ocr_results,
            "decisions": decisions,
            "operator_events": events,
        }
    
    # ==================== Lifecycle ====================
    
    def shutdown(self):
        """Shutdown the repository"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10.0)
        cv_logger._log(LogLevel.INFO, "BRAIN", "Brain repository shutdown")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get repository statistics"""
        return {
            "initialized": self._initialized,
            "queue_size": self._write_queue.qsize(),
            "total_writes": self._total_writes,
            "failed_writes": self._failed_writes,
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {
            "status": "connected" if self._initialized else "disconnected",
            **self.get_stats(),
        }

