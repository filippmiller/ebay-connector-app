"""
CV Brain Router - FastAPI endpoints for Vision Brain system

Provides REST API and WebSocket endpoints for:
- Session management
- Brain status and control
- Operator guidance
- History and analytics
"""

import asyncio
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from ..cv.cv_logger import cv_logger, LogLevel
from ..cv.brain.brain_models import (
    TaskMode,
    SessionStatus,
    OperatorEventType,
    DecisionType,
)
from ..cv.brain.llm_brain import BrainMode

router = APIRouter(prefix="/cv/brain", tags=["Vision Brain"])


# ============================================
# Pydantic Models
# ============================================

class StartSessionRequest(BaseModel):
    """Request to start a new vision session"""
    mode: str = Field("part_number_extraction", description="Task mode")
    expected_object_type: Optional[str] = None
    notes: Optional[str] = None
    brain_mode: str = Field("semi_automatic", description="Brain operation mode")


class OperatorEventRequest(BaseModel):
    """Operator event request"""
    event_type: str = Field(..., description="Event type")
    comment: Optional[str] = None
    payload: dict = Field(default_factory=dict)


class ManualInputRequest(BaseModel):
    """Manual input from operator"""
    field: str = Field("part_number", description="Field name")
    value: str = Field(..., description="Input value")


class SessionResponse(BaseModel):
    """Session response"""
    session_id: str
    status: str
    task_context: Optional[dict] = None
    started_at: str
    ended_at: Optional[str] = None
    stats: dict = {}


class BrainStatusResponse(BaseModel):
    """Brain status response"""
    brain_initialized: bool
    brain_mode: str
    orchestrator_state: str
    session_active: bool
    connected_operators: int
    stats: dict


# ============================================
# Global Brain Instance
# ============================================

_brain_system = None


async def get_brain_system():
    """Get or create the brain system"""
    global _brain_system
    
    if _brain_system is None:
        from ..cv.brain.llm_brain import LLMBrain
        from ..cv.brain.brain_repository import BrainRepository
        from ..cv.brain.vision_brain_orchestrator import VisionBrainOrchestrator
        from ..cv.brain.operator_guidance_service import OperatorGuidanceService
        from ..cv.vision_service import VisionService
        from ..cv.ocr_service import OCRService
        from ..cv.config import cv_settings
        
        # Initialize components
        vision = VisionService()
        vision.load_model()
        
        ocr = OCRService()
        ocr.initialize()
        
        brain = LLMBrain()
        await brain.initialize()
        
        repository = BrainRepository()
        await repository.initialize(
            cv_settings.supabase_url or "",
            cv_settings.supabase_key or "",
        )
        
        orchestrator = VisionBrainOrchestrator(
            vision_service=vision,
            ocr_service=ocr,
            llm_brain=brain,
            repository=repository,
        )
        
        guidance = OperatorGuidanceService(orchestrator)
        
        _brain_system = {
            "brain": brain,
            "repository": repository,
            "orchestrator": orchestrator,
            "guidance": guidance,
            "vision": vision,
            "ocr": ocr,
        }
        
        cv_logger._log(LogLevel.INFO, "BRAIN", "Brain system initialized")
    
    return _brain_system


# ============================================
# REST Endpoints
# ============================================

@router.get("/status", response_model=BrainStatusResponse)
async def get_brain_status():
    """Get brain system status"""
    system = await get_brain_system()
    
    return BrainStatusResponse(
        brain_initialized=system["brain"]._initialized,
        brain_mode=system["brain"]._mode.value,
        orchestrator_state=system["orchestrator"]._session_state.value,
        session_active=system["orchestrator"]._session is not None,
        connected_operators=system["guidance"].get_connected_clients(),
        stats=system["orchestrator"]._stats,
    )


@router.get("/health")
async def brain_health_check():
    """Comprehensive health check"""
    system = await get_brain_system()
    
    return {
        "brain": system["brain"].health_check(),
        "repository": system["repository"].health_check(),
        "orchestrator": system["orchestrator"].health_check(),
        "guidance": system["guidance"].health_check(),
    }


# ==================== Session Management ====================

@router.post("/session/start")
async def start_session(request: StartSessionRequest):
    """Start a new vision session"""
    system = await get_brain_system()
    
    # Parse task mode
    try:
        task_mode = TaskMode(request.mode)
    except ValueError:
        task_mode = TaskMode.PART_NUMBER_EXTRACTION
    
    # Parse brain mode
    try:
        brain_mode = BrainMode(request.brain_mode)
        system["brain"].set_mode(brain_mode)
    except ValueError:
        pass
    
    session_id = await system["orchestrator"].start_session(
        task_mode=task_mode,
        expected_object_type=request.expected_object_type,
        notes=request.notes,
    )
    
    return {
        "session_id": session_id,
        "status": "active",
        "message": "Session started successfully",
    }


@router.post("/session/stop")
async def stop_session():
    """Stop the current session"""
    system = await get_brain_system()
    
    await system["orchestrator"].end_session(SessionStatus.COMPLETED)
    
    return {"status": "stopped", "message": "Session stopped"}


@router.post("/session/pause")
async def pause_session():
    """Pause the current session"""
    system = await get_brain_system()
    system["orchestrator"].pause_session()
    return {"status": "paused"}


@router.post("/session/resume")
async def resume_session():
    """Resume the current session"""
    system = await get_brain_system()
    system["orchestrator"].resume_session()
    return {"status": "resumed"}


@router.get("/session/current")
async def get_current_session():
    """Get current session state"""
    system = await get_brain_system()
    return system["orchestrator"].get_current_state()


@router.get("/session/history")
async def get_session_history():
    """Get current session history"""
    system = await get_brain_system()
    return {"history": system["orchestrator"].get_history()}


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
):
    """List all sessions"""
    system = await get_brain_system()
    
    sessions = await system["repository"].list_sessions(
        limit=limit,
        offset=offset,
        status=status,
    )
    
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}")
async def get_session_details(session_id: str):
    """Get detailed session data"""
    system = await get_brain_system()
    
    details = await system["repository"].get_session_details(session_id)
    
    if not details:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return details


# ==================== Operator Events ====================

@router.post("/operator/event")
async def submit_operator_event(request: OperatorEventRequest):
    """Submit operator event"""
    system = await get_brain_system()
    
    try:
        event_type = OperatorEventType(request.event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event type: {request.event_type}")
    
    await system["orchestrator"].handle_operator_event(
        event_type=event_type,
        payload=request.payload,
        comment=request.comment,
    )
    
    return {"status": "ok", "message": "Event processed"}


@router.post("/operator/manual-input")
async def submit_manual_input(request: ManualInputRequest):
    """Submit manual input from operator"""
    system = await get_brain_system()
    
    await system["orchestrator"].handle_operator_event(
        event_type=OperatorEventType.MANUAL_INPUT,
        payload={"field": request.field, "value": request.value},
        comment=f"Manual {request.field}: {request.value}",
    )
    
    return {"status": "ok", "field": request.field, "value": request.value}


# ==================== Brain Control ====================

@router.post("/brain/mode")
async def set_brain_mode(mode: str):
    """Set brain operation mode"""
    system = await get_brain_system()
    
    try:
        brain_mode = BrainMode(mode)
        system["brain"].set_mode(brain_mode)
        return {"status": "ok", "mode": mode}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")


@router.get("/brain/stats")
async def get_brain_stats():
    """Get brain statistics"""
    system = await get_brain_system()
    return system["brain"].get_stats()


# ==================== Analytics ====================

@router.get("/analytics/detections")
async def get_detection_analytics(session_id: Optional[str] = None):
    """Get detection analytics"""
    system = await get_brain_system()
    
    if session_id:
        detections = await system["repository"].get_session_detections(session_id, limit=500)
    else:
        detections = []
    
    # Group by class
    class_counts = {}
    for det in detections:
        class_name = det.get("class_name", "unknown")
        if class_name not in class_counts:
            class_counts[class_name] = {"count": 0, "confidences": []}
        class_counts[class_name]["count"] += 1
        class_counts[class_name]["confidences"].append(det.get("confidence", 0))
    
    # Calculate averages
    for class_name in class_counts:
        confs = class_counts[class_name]["confidences"]
        class_counts[class_name]["avg_confidence"] = sum(confs) / len(confs) if confs else 0
        del class_counts[class_name]["confidences"]
    
    return {"classes": class_counts, "total": len(detections)}


@router.get("/analytics/ocr")
async def get_ocr_analytics(session_id: Optional[str] = None):
    """Get OCR analytics"""
    system = await get_brain_system()
    
    if session_id:
        ocr_results = await system["repository"].get_session_ocr_results(session_id, limit=500)
    else:
        ocr_results = []
    
    # Extract unique texts
    texts = {}
    for ocr in ocr_results:
        text = ocr.get("cleaned_text", "")
        if text:
            if text not in texts:
                texts[text] = {"count": 0, "max_confidence": 0}
            texts[text]["count"] += 1
            texts[text]["max_confidence"] = max(
                texts[text]["max_confidence"],
                ocr.get("confidence", 0)
            )
    
    return {"texts": texts, "total": len(ocr_results)}


@router.get("/analytics/decisions")
async def get_decision_analytics(session_id: Optional[str] = None):
    """Get brain decision analytics"""
    system = await get_brain_system()
    
    if session_id:
        decisions = await system["repository"].get_session_decisions(session_id, limit=100)
    else:
        decisions = []
    
    stats = {
        "total": len(decisions),
        "by_type": {},
        "by_status": {},
        "avg_latency_ms": 0,
        "total_tokens": 0,
    }
    
    latencies = []
    for dec in decisions:
        dec_type = dec.get("decision_type", "unknown")
        status = dec.get("result_status", "unknown")
        
        stats["by_type"][dec_type] = stats["by_type"].get(dec_type, 0) + 1
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        stats["total_tokens"] += dec.get("tokens_used", 0)
        latencies.append(dec.get("latency_ms", 0))
    
    if latencies:
        stats["avg_latency_ms"] = sum(latencies) / len(latencies)
    
    return stats


# ============================================
# WebSocket Endpoints
# ============================================

@router.websocket("/ws/operator")
async def operator_websocket(websocket: WebSocket):
    """WebSocket endpoint for operator guidance"""
    system = await get_brain_system()
    guidance = system["guidance"]
    
    client_id = await guidance.connect(websocket)
    
    try:
        while True:
            try:
                data = await websocket.receive_json()
                await guidance.handle_message(client_id, data)
            except WebSocketDisconnect:
                break
            except Exception as e:
                cv_logger._log(
                    LogLevel.ERROR, "OPERATOR_UI",
                    f"WebSocket error: {e}"
                )
                await asyncio.sleep(0.1)
    finally:
        await guidance.disconnect(client_id)


@router.websocket("/ws/brain-status")
async def brain_status_websocket(websocket: WebSocket):
    """WebSocket for real-time brain status updates"""
    await websocket.accept()
    system = await get_brain_system()
    
    try:
        while True:
            status = {
                "type": "brain_status",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "brain": system["brain"].get_stats(),
                "orchestrator": system["orchestrator"].get_current_state(),
                "guidance": system["guidance"].health_check(),
            }
            await websocket.send_json(status)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass

