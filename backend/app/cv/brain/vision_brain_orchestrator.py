"""
Vision Brain Orchestrator

The central component that connects:
- Camera/Video stream
- YOLO detector
- OCR reader
- LLM Brain
- Supabase persistence
- Operator UI

Manages the complete workflow of intelligent vision processing.
"""

import asyncio
import time
import uuid
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from collections import deque

from ..cv_logger import cv_logger, LogLevel
from ..camera_service import Frame
from ..vision_service import VisionService, VisionResult, Detection
from ..ocr_service import OCRService, OCRBatchResult

from .brain_models import (
    VisionSession,
    VisionDetection,
    VisionOCRResult,
    BrainDecisionRecord,
    OperatorEvent,
    TaskContext,
    TaskMode,
    FrameData,
    SceneDescription,
    HistoryEntry,
    BoundingBox,
    SessionStatus,
    DecisionType,
    OperatorEventType,
)
from .llm_brain import LLMBrain, BrainMode, BrainRequest, BrainDecision
from .brain_repository import BrainRepository


class SessionState(str, Enum):
    """Current state of a vision session"""
    IDLE = "idle"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    WAITING_FOR_OPERATOR = "waiting_for_operator"
    PROCESSING_RESPONSE = "processing_response"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator"""
    # Processing frequency
    yolo_fps: int = 5  # Run YOLO N times per second
    ocr_frequency: int = 10  # Run OCR every N YOLO detections
    brain_frequency: int = 5  # Call brain every N OCR results
    
    # Thresholds
    min_detection_confidence: float = 0.5
    min_ocr_confidence: float = 0.3
    
    # Classes of interest (None = all)
    target_classes: Optional[List[str]] = None
    
    # Brain settings
    brain_mode: BrainMode = BrainMode.SEMI_AUTOMATIC
    auto_confirm_high_confidence: bool = False
    high_confidence_threshold: float = 0.9
    
    # History
    max_history_entries: int = 20


class VisionBrainOrchestrator:
    """
    The main orchestrator connecting all vision components
    
    Flow:
    1. Receive frames from camera
    2. Run YOLO detection
    3. Run OCR on detected regions
    4. Build scene description
    5. Call LLM brain for decisions
    6. Send instructions to operator
    7. Handle operator responses
    8. Persist everything to Supabase
    """
    
    def __init__(
        self,
        vision_service: VisionService,
        ocr_service: OCRService,
        llm_brain: LLMBrain,
        repository: BrainRepository,
        config: Optional[OrchestratorConfig] = None,
    ):
        self._vision = vision_service
        self._ocr = ocr_service
        self._brain = llm_brain
        self._repository = repository
        self._config = config or OrchestratorConfig()
        
        # Current session
        self._session: Optional[VisionSession] = None
        self._session_state: SessionState = SessionState.IDLE
        self._task_context: Optional[TaskContext] = None
        
        # Processing state
        self._frame_counter = 0
        self._detection_counter = 0
        self._ocr_counter = 0
        self._running = False
        
        # History for brain context
        self._history: deque = deque(maxlen=self._config.max_history_entries)
        
        # Latest data
        self._latest_detections: List[VisionDetection] = []
        self._latest_ocr_results: List[VisionOCRResult] = []
        self._latest_decision: Optional[BrainDecision] = None
        
        # Callbacks
        self._on_instruction: Optional[Callable[[Dict], None]] = None
        self._on_state_change: Optional[Callable[[SessionState], None]] = None
        
        # Statistics
        self._stats = {
            "total_frames": 0,
            "total_detections": 0,
            "total_ocr_results": 0,
            "total_brain_calls": 0,
            "total_operator_events": 0,
        }
    
    # ==================== Session Management ====================
    
    async def start_session(
        self,
        task_mode: TaskMode = TaskMode.PART_NUMBER_EXTRACTION,
        expected_object_type: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Start a new vision session"""
        # Create task context
        self._task_context = TaskContext(
            mode=task_mode,
            expected_object_type=expected_object_type,
            notes=notes,
        )
        
        # Create session
        self._session = VisionSession(
            id=str(uuid.uuid4()),
            status=SessionStatus.ACTIVE,
            task_context=self._task_context,
        )
        
        # Save to Supabase
        await self._repository.create_session(self._session)
        
        # Reset state
        self._history.clear()
        self._frame_counter = 0
        self._detection_counter = 0
        self._ocr_counter = 0
        self._running = True
        self._set_state(SessionState.SCANNING)
        
        cv_logger._log(
            LogLevel.INFO, "ORCHESTRATOR",
            f"Session started: {self._session.id}",
            payload={"mode": task_mode.value, "expected_object": expected_object_type}
        )
        
        # Add initial history entry
        self._add_history("system", "session_started", f"Session started in {task_mode.value} mode")
        
        return self._session.id
    
    async def end_session(
        self,
        status: SessionStatus = SessionStatus.COMPLETED,
        final_result: Optional[Dict] = None,
    ):
        """End the current session"""
        if not self._session:
            return
        
        self._running = False
        self._set_state(SessionState.COMPLETED if status == SessionStatus.COMPLETED else SessionState.IDLE)
        
        # Update session in Supabase
        await self._repository.end_session(
            self._session.id,
            status,
            final_result,
        )
        
        cv_logger._log(
            LogLevel.INFO, "ORCHESTRATOR",
            f"Session ended: {self._session.id}",
            payload={"status": status.value, "final_result": final_result}
        )
        
        self._session = None
        self._task_context = None
    
    def pause_session(self):
        """Pause the current session"""
        if self._session and self._running:
            self._running = False
            self._set_state(SessionState.IDLE)
            self._add_history("system", "session_paused", "Session paused by operator")
    
    def resume_session(self):
        """Resume the current session"""
        if self._session and not self._running:
            self._running = True
            self._set_state(SessionState.SCANNING)
            self._add_history("system", "session_resumed", "Session resumed by operator")
    
    # ==================== Frame Processing ====================
    
    async def process_frame(self, frame: Frame) -> Optional[Dict]:
        """
        Process a single frame through the vision pipeline
        
        Returns instruction for operator if any
        """
        if not self._session or not self._running:
            return None
        
        self._frame_counter += 1
        self._stats["total_frames"] += 1
        
        # Run YOLO detection
        should_run_yolo = (self._frame_counter % max(1, 30 // self._config.yolo_fps) == 0)
        
        if not should_run_yolo:
            return None
        
        self._set_state(SessionState.ANALYZING)
        
        # Get YOLO detections
        vision_result = self._vision.process_frame(frame)
        
        if not vision_result.detections:
            return None
        
        # Convert to our detection format and save
        detections = self._convert_detections(vision_result, frame)
        self._latest_detections = detections
        self._detection_counter += len(detections)
        self._stats["total_detections"] += len(detections)
        
        # Save detections to Supabase
        await self._repository.save_detections(
            [VisionDetection(**d.to_dict()) if isinstance(d, VisionDetection) else d for d in detections]
        )
        
        # Run OCR on text regions
        ocr_results = []
        if vision_result.text_regions and (self._detection_counter % self._config.ocr_frequency == 0):
            ocr_batch = self._ocr.process_text_regions(
                vision_result.text_regions,
                frame.frame_number,
                frame.timestamp,
            )
            ocr_results = self._convert_ocr_results(ocr_batch, frame)
            self._latest_ocr_results = ocr_results
            self._ocr_counter += len(ocr_results)
            self._stats["total_ocr_results"] += len(ocr_results)
            
            # Save OCR results to Supabase
            await self._repository.save_ocr_results(
                [VisionOCRResult(**o.to_dict()) if isinstance(o, VisionOCRResult) else o for o in ocr_results]
            )
        
        # Call brain for decision
        instruction = None
        if self._ocr_counter > 0 and (self._ocr_counter % self._config.brain_frequency == 0):
            instruction = await self._call_brain(frame, detections, ocr_results)
        
        # Update session stats
        await self._repository.update_session(self._session.id, {
            "total_frames": self._stats["total_frames"],
            "total_detections": self._stats["total_detections"],
            "total_ocr_results": self._stats["total_ocr_results"],
            "total_decisions": self._stats["total_brain_calls"],
        })
        
        return instruction
    
    def _convert_detections(self, vision_result: VisionResult, frame: Frame) -> List[VisionDetection]:
        """Convert VisionService detections to VisionDetection objects"""
        detections = []
        
        for det in vision_result.detections:
            # Filter by confidence
            if det.confidence < self._config.min_detection_confidence:
                continue
            
            # Filter by target classes
            if self._config.target_classes and det.class_name not in self._config.target_classes:
                continue
            
            bbox = BoundingBox.from_xyxy(*det.bbox) if det.bbox else None
            
            detection = VisionDetection(
                id=str(uuid.uuid4()),
                session_id=self._session.id,
                frame_id=frame.frame_number,
                timestamp=datetime.now(timezone.utc).isoformat(),
                detector="yolo",
                class_name=det.class_name,
                class_id=det.class_id,
                confidence=det.confidence,
                bbox=bbox,
            )
            detections.append(detection)
        
        return detections
    
    def _convert_ocr_results(self, ocr_batch: OCRBatchResult, frame: Frame) -> List[VisionOCRResult]:
        """Convert OCRService results to VisionOCRResult objects"""
        results = []
        
        for ocr in ocr_batch.results:
            # Filter by confidence
            if ocr.confidence < self._config.min_ocr_confidence:
                continue
            
            bbox = BoundingBox.from_xyxy(*ocr.bbox) if ocr.bbox else None
            
            result = VisionOCRResult(
                id=str(uuid.uuid4()),
                session_id=self._session.id,
                frame_id=frame.frame_number,
                timestamp=datetime.now(timezone.utc).isoformat(),
                crop_bbox=bbox,
                raw_text=ocr.raw_text,
                cleaned_text=ocr.cleaned_text,
                confidence=ocr.confidence,
            )
            results.append(result)
        
        return results
    
    # ==================== Brain Integration ====================
    
    async def _call_brain(
        self,
        frame: Frame,
        detections: List[VisionDetection],
        ocr_results: List[VisionOCRResult],
    ) -> Optional[Dict]:
        """Call the LLM brain for a decision"""
        self._stats["total_brain_calls"] += 1
        
        # Build scene description
        scene = SceneDescription(
            session_id=self._session.id,
            task_context=self._task_context,
            frame=FrameData(
                frame_id=frame.frame_number,
                timestamp=datetime.now(timezone.utc).isoformat(),
                detections=detections,
                ocr_results=ocr_results,
            ),
            history=list(self._history),
        )
        
        # Create request
        request = BrainRequest(
            session_id=self._session.id,
            scene_description=scene.to_dict(),
            mode=self._config.brain_mode,
        )
        
        cv_logger._log(
            LogLevel.DEBUG, "ORCHESTRATOR",
            f"Calling brain for session {self._session.id}",
            payload={
                "detections": len(detections),
                "ocr_results": len(ocr_results),
                "history_entries": len(self._history),
            }
        )
        
        # Call brain
        decision = await self._brain.analyze_scene(request)
        self._latest_decision = decision
        
        # Save decision to Supabase
        decision_record = BrainDecisionRecord(
            id=decision.decision_id,
            session_id=self._session.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_payload=request.to_dict(),
            response_payload=decision.to_dict(),
            decision_type=DecisionType(decision.decision_type) if decision.decision_type in [e.value for e in DecisionType] else DecisionType.NEXT_STEP,
            tokens_used=decision.tokens_used,
            latency_ms=decision.latency_ms,
            error_message=decision.error,
        )
        await self._repository.save_decision(decision_record)
        
        # Handle decision
        if decision.decision_type == "error":
            cv_logger._log(
                LogLevel.ERROR, "ORCHESTRATOR",
                f"Brain error: {decision.error}"
            )
            return None
        
        # Process actions
        instruction = self._process_brain_actions(decision)
        
        return instruction
    
    def _process_brain_actions(self, decision: BrainDecision) -> Optional[Dict]:
        """Process brain actions and build operator instruction"""
        if not decision.actions:
            return None
        
        instructions = []
        extracted_values = []
        
        for action in decision.actions:
            action_type = action.get("type", "")
            message = action.get("message", "")
            value = action.get("value")
            confidence = action.get("confidence", 0)
            
            if action_type == "operator_instruction":
                instructions.append(message)
                self._add_history("brain", "instruction", message)
                
            elif action_type == "mark_candidate_part_number":
                extracted_values.append({
                    "type": "part_number",
                    "value": value,
                    "confidence": confidence,
                })
                self._add_history(
                    "brain", "extraction",
                    f"Found potential part number: {value} (confidence: {confidence:.0%})"
                )
                
            elif action_type == "complete_task":
                self._set_state(SessionState.COMPLETED)
                self._add_history("brain", "completion", message or "Task completed")
        
        if not instructions and not extracted_values:
            return None
        
        # Build instruction for operator
        instruction = {
            "type": "brain_instruction",
            "session_id": self._session.id,
            "decision_id": decision.decision_id,
            "decision_type": decision.decision_type,
            "messages": instructions,
            "extracted_values": extracted_values,
            "confidence": decision.confidence,
            "comments": decision.comments,
            "actions": [
                {"type": "button", "id": "confirm", "label": "Подтвердить"},
                {"type": "button", "id": "reject", "label": "Отклонить"},
                {"type": "button", "id": "retry", "label": "Повторить"},
            ],
        }
        
        self._set_state(SessionState.WAITING_FOR_OPERATOR)
        
        # Notify via callback
        if self._on_instruction:
            self._on_instruction(instruction)
        
        return instruction
    
    # ==================== Operator Events ====================
    
    async def handle_operator_event(
        self,
        event_type: OperatorEventType,
        payload: Optional[Dict] = None,
        comment: Optional[str] = None,
    ):
        """Handle an event from the operator"""
        if not self._session:
            return
        
        self._stats["total_operator_events"] += 1
        self._set_state(SessionState.PROCESSING_RESPONSE)
        
        # Create event
        event = OperatorEvent(
            id=str(uuid.uuid4()),
            session_id=self._session.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            payload=payload or {},
            comment=comment,
            related_decision_id=self._latest_decision.decision_id if self._latest_decision else None,
        )
        
        # Save to Supabase
        await self._repository.save_operator_event(event)
        
        # Add to history
        self._add_history(
            "operator",
            event_type.value,
            comment or f"Operator {event_type.value}"
        )
        
        cv_logger._log(
            LogLevel.INFO, "OPERATOR_UI",
            f"Operator event: {event_type.value}",
            payload={"session_id": self._session.id, "comment": comment}
        )
        
        # Handle specific events
        if event_type == OperatorEventType.ACTION_CONFIRMED:
            # Update decision status
            if self._latest_decision:
                await self._repository.update_decision_status(
                    self._latest_decision.decision_id,
                    "accepted"
                )
            
            # Check if task is complete
            if self._latest_decision and self._latest_decision.decision_type == "final_result":
                await self.end_session(
                    SessionStatus.COMPLETED,
                    {"confirmed_by_operator": True, **self._latest_decision.to_dict()}
                )
            else:
                self._set_state(SessionState.SCANNING)
                
        elif event_type == OperatorEventType.ACTION_REJECTED:
            if self._latest_decision:
                await self._repository.update_decision_status(
                    self._latest_decision.decision_id,
                    "rejected"
                )
            self._set_state(SessionState.SCANNING)
            
        elif event_type == OperatorEventType.CANCEL_REQUESTED:
            await self.end_session(SessionStatus.CANCELLED)
            
        elif event_type == OperatorEventType.PAUSE_REQUESTED:
            self.pause_session()
            
        elif event_type == OperatorEventType.RESUME_REQUESTED:
            self.resume_session()
    
    # ==================== Helpers ====================
    
    def _set_state(self, state: SessionState):
        """Set session state and notify"""
        old_state = self._session_state
        self._session_state = state
        
        if old_state != state:
            cv_logger._log(
                LogLevel.DEBUG, "ORCHESTRATOR",
                f"State: {old_state.value} -> {state.value}"
            )
            
            if self._on_state_change:
                self._on_state_change(state)
    
    def _add_history(self, role: str, entry_type: str, message: str):
        """Add entry to conversation history"""
        entry = HistoryEntry(
            role=role,
            type=entry_type,
            message=message,
        )
        self._history.append(entry)
    
    # ==================== Callbacks ====================
    
    def set_instruction_callback(self, callback: Callable[[Dict], None]):
        """Set callback for operator instructions"""
        self._on_instruction = callback
    
    def set_state_change_callback(self, callback: Callable[[SessionState], None]):
        """Set callback for state changes"""
        self._on_state_change = callback
    
    # ==================== Status ====================
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current orchestrator state"""
        return {
            "session_id": self._session.id if self._session else None,
            "session_state": self._session_state.value,
            "running": self._running,
            "task_mode": self._task_context.mode.value if self._task_context else None,
            "frame_counter": self._frame_counter,
            "detection_counter": self._detection_counter,
            "ocr_counter": self._ocr_counter,
            "history_length": len(self._history),
            "latest_decision": self._latest_decision.to_dict() if self._latest_decision else None,
            "stats": self._stats,
        }
    
    def get_history(self) -> List[Dict]:
        """Get conversation history"""
        return [h.to_dict() for h in self._history]
    
    def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {
            "status": "active" if self._session and self._running else "idle",
            "session_state": self._session_state.value,
            "stats": self._stats,
            "brain": self._brain.health_check(),
            "repository": self._repository.health_check(),
        }

