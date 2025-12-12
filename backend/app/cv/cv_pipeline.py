"""
CV Pipeline - Main Processing Pipeline

Orchestrates the complete computer vision workflow:
1. Camera capture
2. Object detection
3. Text region detection
4. OCR processing
5. Supabase persistence
6. WebSocket streaming
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import threading

from .config import cv_settings
from .cv_logger import cv_logger, LogLevel
from .camera_service import CameraService, Frame
from .vision_service import VisionService, VisionResult
from .ocr_service import OCRService, OCRBatchResult
from .supabase_writer import SupabaseWriter, OCRLogEntry
from .stream_router import StreamRouter, LogStreamRouter


class PipelineState(str, Enum):
    """Pipeline state"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class PipelineStats:
    """Pipeline performance statistics"""
    state: str
    uptime_seconds: float
    frames_processed: int
    detections_total: int
    ocr_results_total: int
    avg_fps: float
    avg_cv_time_ms: float
    avg_ocr_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "frames_processed": self.frames_processed,
            "detections_total": self.detections_total,
            "ocr_results_total": self.ocr_results_total,
            "avg_fps": round(self.avg_fps, 1),
            "avg_cv_time_ms": round(self.avg_cv_time_ms, 2),
            "avg_ocr_time_ms": round(self.avg_ocr_time_ms, 2),
        }


class CVPipeline:
    """
    Main CV Processing Pipeline
    
    Manages the complete workflow from camera capture to data persistence.
    
    Features:
    - Automatic component initialization
    - Graceful startup and shutdown
    - Error recovery
    - Health monitoring
    - Configurable processing intervals
    """
    
    def __init__(self):
        # Services
        self._camera: Optional[CameraService] = None
        self._vision: Optional[VisionService] = None
        self._ocr: Optional[OCRService] = None
        self._supabase: Optional[SupabaseWriter] = None
        self._stream_router: Optional[StreamRouter] = None
        self._log_router: Optional[LogStreamRouter] = None
        
        # State
        self._state: PipelineState = PipelineState.STOPPED
        self._running: bool = False
        self._processing_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._start_time: float = 0.0
        self._frames_processed: int = 0
        self._detections_total: int = 0
        self._ocr_results_total: int = 0
        self._cv_times: List[float] = []
        self._ocr_times: List[float] = []
        
        # Processing counters
        self._frame_counter: int = 0
    
    @property
    def state(self) -> PipelineState:
        return self._state
    
    @property
    def is_running(self) -> bool:
        return self._state == PipelineState.RUNNING
    
    async def initialize(self) -> bool:
        """Initialize all pipeline components"""
        self._state = PipelineState.STARTING
        cv_logger.system("Initializing CV Pipeline...")
        
        try:
            # Initialize camera
            self._camera = CameraService()
            cameras = self._camera.list_cameras()
            cv_logger.system(f"Found {len(cameras)} cameras")
            
            # Initialize vision service
            self._vision = VisionService()
            if not self._vision.load_model():
                cv_logger.system("Vision model not loaded, CV disabled", level=LogLevel.WARNING)
            
            # Initialize OCR service
            self._ocr = OCRService()
            if not self._ocr.initialize():
                cv_logger.system("OCR not initialized, OCR disabled", level=LogLevel.WARNING)
            
            # Initialize Supabase writer
            self._supabase = SupabaseWriter()
            await self._supabase.initialize()
            
            # Register Supabase writer with logger
            cv_logger.set_supabase_writer(self._supabase)
            
            # Initialize stream router
            self._stream_router = StreamRouter(self._camera, self._vision)
            
            # Initialize log router
            self._log_router = LogStreamRouter()
            cv_logger.register_ws_callback(self._log_router.get_callback())
            
            cv_logger.system("CV Pipeline initialized successfully")
            return True
            
        except Exception as e:
            self._state = PipelineState.ERROR
            cv_logger.system(f"Pipeline initialization failed: {e}", level=LogLevel.ERROR)
            return False
    
    async def start(self) -> bool:
        """Start the processing pipeline"""
        if self._state == PipelineState.RUNNING:
            cv_logger.system("Pipeline already running", level=LogLevel.WARNING)
            return True
        
        try:
            # Connect camera
            if not self._camera.connect():
                raise ConnectionError("Failed to connect camera")
            
            # Start camera streaming
            if not self._camera.start_streaming():
                raise ConnectionError("Failed to start camera streaming")
            
            # Start processing loop
            self._running = True
            self._start_time = time.time()
            self._state = PipelineState.RUNNING
            
            self._processing_task = asyncio.create_task(self._processing_loop())
            
            cv_logger.system("CV Pipeline started")
            return True
            
        except Exception as e:
            self._state = PipelineState.ERROR
            cv_logger.system(f"Failed to start pipeline: {e}", level=LogLevel.ERROR)
            return False
    
    async def stop(self):
        """Stop the processing pipeline"""
        cv_logger.system("Stopping CV Pipeline...")
        
        self._running = False
        
        # Cancel processing task
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        # Stop stream router
        if self._stream_router:
            self._stream_router.stop_broadcast_loop()
        
        # Stop camera
        if self._camera:
            self._camera.stop_streaming()
            self._camera.disconnect()
        
        # Shutdown Supabase writer
        if self._supabase:
            self._supabase.shutdown()
        
        self._state = PipelineState.STOPPED
        cv_logger.system("CV Pipeline stopped")
    
    async def pause(self):
        """Pause processing"""
        if self._state == PipelineState.RUNNING:
            self._state = PipelineState.PAUSED
            cv_logger.system("CV Pipeline paused")
    
    async def resume(self):
        """Resume processing"""
        if self._state == PipelineState.PAUSED:
            self._state = PipelineState.RUNNING
            cv_logger.system("CV Pipeline resumed")
    
    async def _processing_loop(self):
        """Main processing loop"""
        cv_logger.system("Processing loop started")
        
        while self._running:
            try:
                if self._state == PipelineState.PAUSED:
                    await asyncio.sleep(0.1)
                    continue
                
                # Get frame from camera
                frame = self._camera.get_frame(timeout=0.1)
                
                if frame is None:
                    await asyncio.sleep(0.01)
                    continue
                
                self._frame_counter += 1
                self._frames_processed += 1
                
                vision_result = None
                ocr_result = None
                
                # Run CV processing on scheduled frames
                if (
                    self._vision and
                    self._vision._model_loaded and
                    self._frame_counter % cv_settings.process_every_n_frames == 0
                ):
                    start_cv = time.time()
                    vision_result = self._vision.process_frame(frame)
                    self._cv_times.append((time.time() - start_cv) * 1000)
                    
                    if len(self._cv_times) > 100:
                        self._cv_times = self._cv_times[-100:]
                    
                    self._detections_total += len(vision_result.detections)
                
                # Run OCR on scheduled frames
                if (
                    self._ocr and
                    self._ocr._initialized and
                    vision_result and
                    vision_result.text_regions and
                    self._frame_counter % cv_settings.ocr_every_n_frames == 0
                ):
                    start_ocr = time.time()
                    ocr_result = self._ocr.process_text_regions(
                        vision_result.text_regions,
                        frame.frame_number,
                        frame.timestamp,
                    )
                    self._ocr_times.append((time.time() - start_ocr) * 1000)
                    
                    if len(self._ocr_times) > 100:
                        self._ocr_times = self._ocr_times[-100:]
                    
                    self._ocr_results_total += len(ocr_result.results)
                    
                    # Persist OCR results to Supabase
                    await self._persist_ocr_results(ocr_result, frame)
                
                # Broadcast frame to connected clients
                if self._stream_router:
                    await self._stream_router.broadcast_frame(frame, vision_result)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                cv_logger.system(f"Processing error: {e}", level=LogLevel.ERROR)
                await asyncio.sleep(0.1)
        
        cv_logger.system("Processing loop ended")
    
    async def _persist_ocr_results(self, ocr_result: OCRBatchResult, frame: Frame):
        """Persist OCR results to Supabase"""
        if not self._supabase or not ocr_result.results:
            return
        
        for i, result in enumerate(ocr_result.results):
            # Upload crop if available
            crop_url = None
            # Crops are part of text regions, would need to track them
            
            entry = OCRLogEntry(
                raw_text=result.raw_text,
                cleaned_text=result.cleaned_text,
                confidence_score=result.confidence,
                source_frame_number=frame.frame_number,
                crop_image_url=crop_url,
            )
            
            await self._supabase.write_ocr_result(entry)
    
    def get_stats(self) -> PipelineStats:
        """Get pipeline statistics"""
        uptime = time.time() - self._start_time if self._start_time else 0
        avg_fps = self._frames_processed / uptime if uptime > 0 else 0
        avg_cv = sum(self._cv_times) / len(self._cv_times) if self._cv_times else 0
        avg_ocr = sum(self._ocr_times) / len(self._ocr_times) if self._ocr_times else 0
        
        return PipelineStats(
            state=self._state.value,
            uptime_seconds=uptime,
            frames_processed=self._frames_processed,
            detections_total=self._detections_total,
            ocr_results_total=self._ocr_results_total,
            avg_fps=avg_fps,
            avg_cv_time_ms=avg_cv,
            avg_ocr_time_ms=avg_ocr,
        )
    
    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        return {
            "pipeline": {
                "state": self._state.value,
                "running": self.is_running,
                "stats": self.get_stats().to_dict(),
            },
            "camera": self._camera.health_check() if self._camera else {"status": "not_initialized"},
            "vision": self._vision.health_check() if self._vision else {"status": "not_initialized"},
            "ocr": self._ocr.health_check() if self._ocr else {"status": "not_initialized"},
            "supabase": self._supabase.health_check() if self._supabase else {"status": "not_initialized"},
            "stream": self._stream_router.health_check() if self._stream_router else {"status": "not_initialized"},
            "metrics": cv_logger.get_metrics(),
        }
    
    # Service accessors
    @property
    def camera(self) -> Optional[CameraService]:
        return self._camera
    
    @property
    def vision(self) -> Optional[VisionService]:
        return self._vision
    
    @property
    def ocr(self) -> Optional[OCRService]:
        return self._ocr
    
    @property
    def supabase(self) -> Optional[SupabaseWriter]:
        return self._supabase
    
    @property
    def stream_router(self) -> Optional[StreamRouter]:
        return self._stream_router
    
    @property
    def log_router(self) -> Optional[LogStreamRouter]:
        return self._log_router


# Global pipeline instance
cv_pipeline: Optional[CVPipeline] = None


async def get_pipeline() -> CVPipeline:
    """Get or create the global pipeline instance"""
    global cv_pipeline
    if cv_pipeline is None:
        cv_pipeline = CVPipeline()
        await cv_pipeline.initialize()
    return cv_pipeline

