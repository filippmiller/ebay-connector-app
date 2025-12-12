"""
Brain Layer Data Models

Defines all data structures for the vision brain system:
- Sessions
- Detections
- OCR Results
- Brain Decisions
- Operator Events
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class SessionStatus(str, Enum):
    """Vision session status"""
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskMode(str, Enum):
    """Task mode for brain processing"""
    PART_NUMBER_EXTRACTION = "part_number_extraction"
    COMPONENT_IDENTIFICATION = "component_identification"
    QUALITY_INSPECTION = "quality_inspection"
    INVENTORY_SCAN = "inventory_scan"
    GENERAL_RECOGNITION = "general_recognition"


class DecisionType(str, Enum):
    """Type of brain decision"""
    NEXT_STEP = "next_step"
    FINAL_RESULT = "final_result"
    CLARIFICATION_NEEDED = "clarification_needed"
    ERROR = "error"
    WAITING = "waiting"


class ActionType(str, Enum):
    """Type of action from brain"""
    OPERATOR_INSTRUCTION = "operator_instruction"
    MARK_CANDIDATE_PART_NUMBER = "mark_candidate_part_number"
    CONFIRM_DETECTION = "confirm_detection"
    REQUEST_REPOSITIONING = "request_repositioning"
    REQUEST_ZOOM = "request_zoom"
    CAPTURE_FRAME = "capture_frame"
    COMPLETE_TASK = "complete_task"
    ABORT_TASK = "abort_task"


class OperatorEventType(str, Enum):
    """Type of operator event"""
    ACTION_CONFIRMED = "action_confirmed"
    ACTION_REJECTED = "action_rejected"
    MANUAL_INPUT = "manual_input"
    PAUSE_REQUESTED = "pause_requested"
    RESUME_REQUESTED = "resume_requested"
    CANCEL_REQUESTED = "cancel_requested"
    COMMENT_ADDED = "comment_added"


@dataclass
class BoundingBox:
    """Bounding box coordinates"""
    x: int
    y: int
    w: int
    h: int
    
    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BoundingBox":
        return cls(x=data["x"], y=data["y"], w=data["w"], h=data["h"])
    
    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> "BoundingBox":
        return cls(x=x1, y=y1, w=x2-x1, h=y2-y1)


@dataclass
class VisionDetection:
    """Single YOLO detection result"""
    id: str
    session_id: str
    frame_id: int
    timestamp: str
    detector: str = "yolo"
    class_name: str = ""
    class_id: int = 0
    confidence: float = 0.0
    bbox: Optional[BoundingBox] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "detector": self.detector,
            "class_name": self.class_name,
            "class_id": self.class_id,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "extra": self.extra,
        }


@dataclass
class VisionOCRResult:
    """OCR result linked to detection"""
    id: str
    session_id: str
    frame_id: int
    timestamp: str
    crop_bbox: Optional[BoundingBox] = None
    raw_text: str = ""
    cleaned_text: str = ""
    confidence: float = 0.0
    source_detection_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "crop_bbox": self.crop_bbox.to_dict() if self.crop_bbox else None,
            "raw_text": self.raw_text,
            "cleaned_text": self.cleaned_text,
            "confidence": self.confidence,
            "source_detection_id": self.source_detection_id,
            "metadata": self.metadata,
        }


@dataclass
class BrainAction:
    """Single action from brain decision"""
    type: ActionType
    message: str = ""
    value: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type.value,
            "message": self.message,
        }
        if self.value is not None:
            result["value"] = self.value
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class BrainDecisionRecord:
    """Record of brain decision stored in Supabase"""
    id: str
    session_id: str
    timestamp: str
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]
    decision_type: DecisionType
    result_status: str = "pending"  # pending, accepted, rejected
    tokens_used: int = 0
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "request_payload": self.request_payload,
            "response_payload": self.response_payload,
            "decision_type": self.decision_type.value if isinstance(self.decision_type, DecisionType) else self.decision_type,
            "result_status": self.result_status,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
        }


@dataclass
class OperatorEvent:
    """Event from operator (confirmation, rejection, comment)"""
    id: str
    session_id: str
    timestamp: str
    event_type: OperatorEventType
    payload: Dict[str, Any] = field(default_factory=dict)
    comment: Optional[str] = None
    related_decision_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value if isinstance(self.event_type, OperatorEventType) else self.event_type,
            "payload": self.payload,
            "comment": self.comment,
            "related_decision_id": self.related_decision_id,
        }


@dataclass
class TaskContext:
    """Context for the current task"""
    mode: TaskMode
    expected_object_type: Optional[str] = None
    notes: Optional[str] = None
    target_fields: List[str] = field(default_factory=list)  # e.g., ["part_number", "serial", "model"]
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "expected_object_type": self.expected_object_type,
            "notes": self.notes,
            "target_fields": self.target_fields,
            "constraints": self.constraints,
        }


@dataclass
class HistoryEntry:
    """Single entry in conversation history"""
    role: str  # "brain" or "operator"
    type: str  # "instruction", "action_confirmed", "comment", etc.
    message: str
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "type": self.type,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class FrameData:
    """Frame data with detections and OCR results"""
    frame_id: int
    timestamp: str
    detections: List[VisionDetection] = field(default_factory=list)
    ocr_results: List[VisionOCRResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "detections": [d.to_dict() for d in self.detections],
            "ocr_results": [o.to_dict() for o in self.ocr_results],
        }


@dataclass
class SceneDescription:
    """Complete scene description for LLM brain"""
    session_id: str
    task_context: TaskContext
    frame: FrameData
    history: List[HistoryEntry] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_context": self.task_context.to_dict(),
            "frame": self.frame.to_dict(),
            "history": [h.to_dict() for h in self.history],
        }


@dataclass
class VisionSession:
    """Vision processing session"""
    id: str
    status: SessionStatus = SessionStatus.CREATED
    task_context: Optional[TaskContext] = None
    started_at: str = ""
    ended_at: Optional[str] = None
    total_frames: int = 0
    total_detections: int = 0
    total_ocr_results: int = 0
    total_decisions: int = 0
    final_result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value if isinstance(self.status, SessionStatus) else self.status,
            "task_context": self.task_context.to_dict() if self.task_context else None,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_frames": self.total_frames,
            "total_detections": self.total_detections,
            "total_ocr_results": self.total_ocr_results,
            "total_decisions": self.total_decisions,
            "final_result": self.final_result,
            "metadata": self.metadata,
        }

