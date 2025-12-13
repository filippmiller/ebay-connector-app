"""
CV Camera Router - FastAPI endpoints for Computer Vision module

Provides REST API and WebSocket endpoints for:
- Camera control
- Video streaming
- CV pipeline management
- OCR results
- Debug console
"""

import asyncio
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..cv.cv_pipeline import CVPipeline, get_pipeline, PipelineState
from ..cv.config import cv_settings, CameraMode, OCREngine
from ..cv.cv_logger import cv_logger, LogLevel
from ..cv.stream_router import StreamMode

router = APIRouter(prefix="/cv", tags=["Computer Vision"])


# ============================================
# Pydantic Models
# ============================================

class CameraConfig(BaseModel):
    """Camera configuration"""
    mode: CameraMode = CameraMode.UVC
    device_id: int = 0
    rtmp_url: Optional[str] = None
    rtsp_url: Optional[str] = None
    width: int = 1920
    height: int = 1080
    fps: int = 30


class CVConfig(BaseModel):
    """CV processing configuration"""
    yolo_model: str = "yolov8n.pt"
    confidence: float = 0.5
    process_every_n_frames: int = 5
    ocr_every_n_frames: int = 30
    ocr_engine: OCREngine = OCREngine.EASYOCR
    ocr_languages: List[str] = ["en", "ru"]


class PipelineCommand(BaseModel):
    """Pipeline control command"""
    action: str = Field(..., description="start, stop, pause, resume")


class StreamConfig(BaseModel):
    """Stream configuration"""
    mode: StreamMode = StreamMode.RAW
    quality: int = Field(80, ge=1, le=100)
    max_fps: int = Field(30, ge=1, le=60)


class OCRLogResponse(BaseModel):
    """OCR log entry response"""
    id: str
    timestamp: str
    raw_text: str
    cleaned_text: str
    confidence_score: float
    source_frame_number: int
    camera_id: str
    crop_image_url: Optional[str] = None


class LogEntry(BaseModel):
    """Log entry response"""
    timestamp: str
    level: str
    subsystem: str
    message: str
    payload: dict = {}


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    pipeline: dict
    camera: dict
    vision: dict
    ocr: dict
    supabase: dict
    stream: dict
    metrics: dict


# ============================================
# Pipeline Instance Management
# ============================================

_pipeline: Optional[CVPipeline] = None


async def get_cv_pipeline() -> CVPipeline:
    """Get or create CV pipeline instance"""
    global _pipeline
    if _pipeline is None:
        _pipeline = await get_pipeline()
    return _pipeline


# ============================================
# REST Endpoints
# ============================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Get comprehensive health status of CV module"""
    pipeline = await get_cv_pipeline()
    return pipeline.health_check()


@router.get("/status")
async def get_status():
    """Get current pipeline status"""
    pipeline = await get_cv_pipeline()
    stats = pipeline.get_stats()
    return {
        "state": pipeline.state.value,
        "stats": stats.to_dict(),
        "camera_connected": pipeline.camera.is_connected if pipeline.camera else False,
    }


@router.post("/pipeline/start")
async def start_pipeline():
    """Start the CV processing pipeline"""
    pipeline = await get_cv_pipeline()
    
    if pipeline.is_running:
        return {"status": "already_running", "message": "Pipeline is already running"}
    
    success = await pipeline.start()
    
    if success:
        cv_logger.system("Pipeline started via API")
        return {"status": "started", "message": "CV pipeline started successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start pipeline")


@router.post("/pipeline/stop")
async def stop_pipeline():
    """Stop the CV processing pipeline"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.is_running:
        return {"status": "already_stopped", "message": "Pipeline is already stopped"}
    
    await pipeline.stop()
    cv_logger.system("Pipeline stopped via API")
    return {"status": "stopped", "message": "CV pipeline stopped"}


@router.post("/pipeline/pause")
async def pause_pipeline():
    """Pause CV processing"""
    pipeline = await get_cv_pipeline()
    await pipeline.pause()
    return {"status": "paused"}


@router.post("/pipeline/resume")
async def resume_pipeline():
    """Resume CV processing"""
    pipeline = await get_cv_pipeline()
    await pipeline.resume()
    return {"status": "resumed"}


@router.post("/pipeline/command")
async def pipeline_command(cmd: PipelineCommand):
    """Execute pipeline command"""
    pipeline = await get_cv_pipeline()
    
    actions = {
        "start": pipeline.start,
        "stop": pipeline.stop,
        "pause": pipeline.pause,
        "resume": pipeline.resume,
    }
    
    if cmd.action not in actions:
        raise HTTPException(status_code=400, detail=f"Invalid action: {cmd.action}")
    
    await actions[cmd.action]()
    return {"status": "ok", "action": cmd.action}


# ============================================
# Camera Endpoints
# ============================================

@router.get("/camera/list")
async def list_cameras():
    """List available cameras"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.camera:
        raise HTTPException(status_code=500, detail="Camera service not initialized")
    
    cameras = pipeline.camera.list_cameras()
    return {
        "cameras": [
            {
                "device_id": c.device_id,
                "name": c.name,
                "width": c.width,
                "height": c.height,
                "fps": c.fps,
            }
            for c in cameras
        ]
    }


@router.get("/camera/status")
async def camera_status():
    """Get camera status"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.camera:
        return {"status": "not_initialized"}
    
    return pipeline.camera.health_check()


@router.post("/camera/connect")
async def connect_camera(config: Optional[CameraConfig] = None):
    """Connect to camera"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.camera:
        raise HTTPException(status_code=500, detail="Camera service not initialized")
    
    # Apply config if provided
    if config:
        cv_settings.camera_mode = config.mode
        cv_settings.camera_device_id = config.device_id
        cv_settings.camera_rtmp_url = config.rtmp_url
        cv_settings.camera_rtsp_url = config.rtsp_url
        cv_settings.camera_width = config.width
        cv_settings.camera_height = config.height
        cv_settings.camera_fps = config.fps
    
    success = pipeline.camera.connect()
    
    if success:
        return {"status": "connected", "info": pipeline.camera.camera_info}
    else:
        raise HTTPException(status_code=500, detail="Failed to connect to camera")


@router.post("/camera/disconnect")
async def disconnect_camera():
    """Disconnect from camera"""
    pipeline = await get_cv_pipeline()
    
    if pipeline.camera:
        pipeline.camera.disconnect()
    
    return {"status": "disconnected"}


# ============================================
# CV/Vision Endpoints
# ============================================

@router.get("/vision/status")
async def vision_status():
    """Get vision service status"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.vision:
        return {"status": "not_initialized"}
    
    return pipeline.vision.health_check()


@router.get("/vision/stats")
async def vision_stats():
    """Get vision processing statistics"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.vision:
        return {"status": "not_initialized"}
    
    return pipeline.vision.get_stats()


# ============================================
# OCR Endpoints
# ============================================

@router.get("/ocr/status")
async def ocr_status():
    """Get OCR service status"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.ocr:
        return {"status": "not_initialized"}
    
    return pipeline.ocr.health_check()


@router.get("/ocr/stats")
async def ocr_stats():
    """Get OCR processing statistics"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.ocr:
        return {"status": "not_initialized"}
    
    return pipeline.ocr.get_stats()


@router.get("/ocr/logs")
async def get_ocr_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    camera_id: Optional[str] = None,
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
):
    """Get OCR log entries from Supabase"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.supabase or not pipeline.supabase._initialized:
        # Return empty if Supabase not connected
        return {"logs": [], "total": 0}
    
    try:
        query = pipeline.supabase._client.table("camera_ocr_logs").select("*")
        
        if camera_id:
            query = query.eq("camera_id", camera_id)
        
        if min_confidence is not None:
            query = query.gte("confidence_score", min_confidence)
        
        query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)
        
        result = query.execute()
        
        return {
            "logs": result.data,
            "count": len(result.data),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        cv_logger.error(f"Failed to fetch OCR logs: {e}", subsystem="SUPABASE")
        return {"logs": [], "error": str(e)}


# ============================================
# Logs/Debug Endpoints
# ============================================

@router.get("/logs/recent")
async def get_recent_logs(count: int = Query(50, ge=1, le=500)):
    """Get recent log entries from memory buffer"""
    return {"logs": cv_logger.get_recent_logs(count)}


@router.get("/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    level: Optional[str] = None,
    subsystem: Optional[str] = None,
):
    """Get log entries from Supabase"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.supabase or not pipeline.supabase._initialized:
        return {"logs": cv_logger.get_recent_logs(limit)}
    
    try:
        query = pipeline.supabase._client.table("camera_logs").select("*")
        
        if level:
            query = query.eq("level", level)
        
        if subsystem:
            query = query.eq("subsystem", subsystem)
        
        query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)
        
        result = query.execute()
        
        return {
            "logs": result.data,
            "count": len(result.data),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        return {"logs": cv_logger.get_recent_logs(limit), "error": str(e)}


@router.get("/metrics")
async def get_metrics():
    """Get current metrics"""
    return cv_logger.get_metrics()


# ============================================
# Configuration Endpoints
# ============================================

@router.get("/config")
async def get_config():
    """Get current CV configuration"""
    return {
        "camera": {
            "mode": cv_settings.camera_mode.value,
            "device_id": cv_settings.camera_device_id,
            "width": cv_settings.camera_width,
            "height": cv_settings.camera_height,
            "fps": cv_settings.camera_fps,
        },
        "vision": {
            "yolo_model": cv_settings.yolo_model,
            "confidence": cv_settings.yolo_confidence,
            "device": cv_settings.yolo_device,
        },
        "ocr": {
            "engine": cv_settings.ocr_engine.value,
            "languages": cv_settings.ocr_languages,
            "confidence_threshold": cv_settings.ocr_confidence_threshold,
        },
        "processing": {
            "process_every_n_frames": cv_settings.process_every_n_frames,
            "ocr_every_n_frames": cv_settings.ocr_every_n_frames,
        },
        "stream": {
            "quality": cv_settings.stream_quality,
            "max_fps": cv_settings.stream_max_fps,
        },
    }


@router.put("/config")
async def update_config(config: CVConfig):
    """Update CV configuration"""
    cv_settings.yolo_model = config.yolo_model
    cv_settings.yolo_confidence = config.confidence
    cv_settings.process_every_n_frames = config.process_every_n_frames
    cv_settings.ocr_every_n_frames = config.ocr_every_n_frames
    cv_settings.ocr_engine = config.ocr_engine
    cv_settings.ocr_languages = config.ocr_languages
    
    cv_logger.system("Configuration updated via API", payload=config.model_dump())
    
    return {"status": "updated", "config": config.model_dump()}


# ============================================
# WebSocket Endpoints
# ============================================

@router.websocket("/stream")
async def video_stream(websocket: WebSocket, mode: str = "raw"):
    """WebSocket endpoint for live video streaming"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.stream_router:
        await websocket.close(code=1011, reason="Stream router not initialized")
        return
    
    client_id = str(uuid.uuid4())
    stream_mode = StreamMode(mode) if mode in [m.value for m in StreamMode] else StreamMode.RAW
    
    try:
        await pipeline.stream_router.connect(websocket, client_id, stream_mode)
        
        # Start broadcast loop if not running
        if not pipeline.stream_router._running:
            asyncio.create_task(pipeline.stream_router.start_broadcast_loop())
        
        # Keep connection alive and handle client messages
        while True:
            try:
                data = await websocket.receive_json()
                await pipeline.stream_router.handle_client_message(client_id, data)
            except WebSocketDisconnect:
                break
            except Exception:
                await asyncio.sleep(0.1)
                
    except WebSocketDisconnect:
        pass
    finally:
        await pipeline.stream_router.disconnect(client_id)


@router.websocket("/logs/stream")
async def logs_stream(websocket: WebSocket):
    """WebSocket endpoint for live log streaming"""
    pipeline = await get_cv_pipeline()
    
    if not pipeline.log_router:
        await websocket.close(code=1011, reason="Log router not initialized")
        return
    
    client_id = str(uuid.uuid4())
    
    try:
        await pipeline.log_router.connect(websocket, client_id)
        
        # Send recent logs first
        recent = cv_logger.get_recent_logs(50)
        await websocket.send_json({"type": "history", "logs": recent})
        
        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_json()
                # Handle any client commands if needed
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
            except Exception:
                await asyncio.sleep(0.1)
                
    except WebSocketDisconnect:
        pass
    finally:
        await pipeline.log_router.disconnect(client_id)


@router.websocket("/metrics/stream")
async def metrics_stream(websocket: WebSocket):
    """WebSocket endpoint for live metrics streaming"""
    await websocket.accept()
    
    try:
        while True:
            metrics = cv_logger.get_metrics()
            pipeline = await get_cv_pipeline()
            
            data = {
                "type": "metrics",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
                "pipeline_stats": pipeline.get_stats().to_dict() if pipeline else None,
            }
            
            await websocket.send_json(data)
            await asyncio.sleep(1)  # Update every second
            
    except WebSocketDisconnect:
        pass

