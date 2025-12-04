"""
Vision Service - Object Detection with YOLOv8

Uses Ultralytics YOLOv8 for real-time object detection.
Supports detection of objects and text regions for OCR processing.
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import threading
from queue import Queue, Empty

try:
    import cv2
except ImportError:
    cv2 = None

from .config import cv_settings
from .cv_logger import cv_logger, LogLevel
from .camera_service import Frame


@dataclass
class Detection:
    """Single object detection result"""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    center: Tuple[int, int]
    area: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox),
            "center": list(self.center),
            "area": self.area,
        }


@dataclass
class TextRegion:
    """Detected text region for OCR"""
    bbox: Tuple[int, int, int, int]
    confidence: float
    cropped_image: Optional[np.ndarray] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "confidence": round(self.confidence, 3),
        }


@dataclass
class VisionResult:
    """Complete vision analysis result"""
    frame_number: int
    timestamp: float
    detections: List[Detection] = field(default_factory=list)
    text_regions: List[TextRegion] = field(default_factory=list)
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_number": self.frame_number,
            "timestamp": self.timestamp,
            "detections": [d.to_dict() for d in self.detections],
            "text_regions": [t.to_dict() for t in self.text_regions],
            "processing_time_ms": round(self.processing_time_ms, 2),
            "detection_count": len(self.detections),
            "text_region_count": len(self.text_regions),
        }


class VisionService:
    """
    Computer Vision Service using YOLOv8
    
    Features:
    - Real-time object detection
    - Text region detection for OCR
    - Configurable confidence thresholds
    - GPU acceleration support
    - Batch processing capability
    """
    
    def __init__(self):
        self._model = None
        self._model_loaded: bool = False
        self._lock = threading.Lock()
        self._processing_queue: Queue = Queue(maxsize=10)
        self._result_queue: Queue = Queue(maxsize=10)
        
        # YOLO class names (COCO dataset)
        self._class_names: List[str] = []
        
        # Text detection using EAST or custom model
        self._text_detector = None
        
        # Performance tracking
        self._total_processed: int = 0
        self._avg_processing_time: float = 0.0
    
    def load_model(self) -> bool:
        """Load YOLO model"""
        try:
            from ultralytics import YOLO
            
            cv_logger.cv(f"Loading YOLO model: {cv_settings.yolo_model}")
            
            self._model = YOLO(cv_settings.yolo_model)
            
            # Move to specified device
            if cv_settings.yolo_device == "cuda":
                import torch
                if torch.cuda.is_available():
                    self._model.to("cuda")
                    cv_logger.cv("Model loaded on CUDA")
                else:
                    cv_logger.cv("CUDA not available, using CPU", level=LogLevel.WARNING)
            
            # Get class names
            self._class_names = self._model.names if hasattr(self._model, 'names') else []
            
            self._model_loaded = True
            cv_logger.set_status("cv", "ready")
            cv_logger.cv(
                "YOLO model loaded successfully",
                payload={
                    "model": cv_settings.yolo_model,
                    "device": cv_settings.yolo_device,
                    "classes": len(self._class_names),
                }
            )
            
            return True
            
        except ImportError:
            cv_logger.cv(
                "Ultralytics not installed. Install with: pip install ultralytics",
                level=LogLevel.ERROR
            )
            return False
        except Exception as e:
            cv_logger.cv(f"Failed to load YOLO model: {e}", level=LogLevel.ERROR)
            return False
    
    def load_text_detector(self) -> bool:
        """Load text detection model (EAST or similar)"""
        try:
            # Try to load EAST text detector
            # If not available, we'll use text detection from YOLO or skip
            cv_logger.cv("Text detector ready (using contour-based detection)")
            return True
        except Exception as e:
            cv_logger.cv(f"Failed to load text detector: {e}", level=LogLevel.WARNING)
            return False
    
    def detect_objects(self, frame: Frame) -> List[Detection]:
        """Detect objects in frame using YOLO"""
        if not self._model_loaded:
            return []
        
        try:
            # Run inference
            results = self._model(
                frame.data,
                conf=cv_settings.yolo_confidence,
                iou=cv_settings.yolo_iou_threshold,
                classes=cv_settings.yolo_classes,
                verbose=False,
            )
            
            detections = []
            
            for result in results:
                if result.boxes is None:
                    continue
                    
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy().astype(int)
                
                for box, conf, class_id in zip(boxes, confidences, class_ids):
                    x1, y1, x2, y2 = map(int, box)
                    center = ((x1 + x2) // 2, (y1 + y2) // 2)
                    area = (x2 - x1) * (y2 - y1)
                    
                    class_name = self._class_names.get(class_id, f"class_{class_id}") \
                        if isinstance(self._class_names, dict) \
                        else (self._class_names[class_id] if class_id < len(self._class_names) else f"class_{class_id}")
                    
                    detections.append(Detection(
                        class_id=class_id,
                        class_name=class_name,
                        confidence=float(conf),
                        bbox=(x1, y1, x2, y2),
                        center=center,
                        area=area,
                    ))
            
            return detections
            
        except Exception as e:
            cv_logger.cv(f"Object detection error: {e}", level=LogLevel.ERROR)
            return []
    
    def detect_text_regions(self, frame: Frame) -> List[TextRegion]:
        """Detect regions likely containing text"""
        if cv2 is None:
            return []
        
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(frame.data, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Morphological operations to connect text regions
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            text_regions = []
            
            for contour in contours:
                area = cv2.contourArea(contour)
                
                if area < cv_settings.text_min_area:
                    continue
                
                x, y, w, h = cv2.boundingRect(contour)
                
                # Filter by aspect ratio (text regions are usually wider than tall)
                aspect_ratio = w / h if h > 0 else 0
                if aspect_ratio < 0.5 or aspect_ratio > 20:
                    continue
                
                # Add padding
                pad = cv_settings.text_padding
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(frame.width, x + w + pad)
                y2 = min(frame.height, y + h + pad)
                
                # Crop the region
                cropped = frame.data[y1:y2, x1:x2].copy()
                
                text_regions.append(TextRegion(
                    bbox=(x1, y1, x2, y2),
                    confidence=0.5,  # Contour-based detection doesn't have confidence
                    cropped_image=cropped,
                ))
            
            return text_regions
            
        except Exception as e:
            cv_logger.cv(f"Text region detection error: {e}", level=LogLevel.ERROR)
            return []
    
    def process_frame(self, frame: Frame) -> VisionResult:
        """Process a single frame with full CV pipeline"""
        start_time = time.time()
        
        result = VisionResult(
            frame_number=frame.frame_number,
            timestamp=frame.timestamp,
        )
        
        # Object detection
        result.detections = self.detect_objects(frame)
        
        # Text region detection
        if cv_settings.text_detection_enabled:
            result.text_regions = self.detect_text_regions(frame)
        
        # Calculate processing time
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        # Update performance metrics
        self._total_processed += 1
        self._avg_processing_time = (
            (self._avg_processing_time * (self._total_processed - 1) + result.processing_time_ms)
            / self._total_processed
        )
        
        cv_logger.increment_frames()
        
        if result.detections or result.text_regions:
            cv_logger.cv(
                f"Frame {frame.frame_number}: {len(result.detections)} objects, {len(result.text_regions)} text regions",
                level=LogLevel.DEBUG,
                payload=result.to_dict(),
            )
        
        return result
    
    def draw_detections(
        self,
        frame: np.ndarray,
        result: VisionResult,
        draw_objects: bool = True,
        draw_text_regions: bool = True,
    ) -> np.ndarray:
        """Draw detection results on frame"""
        if cv2 is None:
            return frame
        
        output = frame.copy()
        
        # Draw object detections
        if draw_objects:
            for det in result.detections:
                x1, y1, x2, y2 = det.bbox
                
                # Draw bounding box
                cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw label
                label = f"{det.class_name}: {det.confidence:.2f}"
                (label_w, label_h), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                )
                cv2.rectangle(
                    output,
                    (x1, y1 - label_h - 10),
                    (x1 + label_w, y1),
                    (0, 255, 0),
                    -1,
                )
                cv2.putText(
                    output, label,
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 1,
                )
        
        # Draw text regions
        if draw_text_regions:
            for region in result.text_regions:
                x1, y1, x2, y2 = region.bbox
                cv2.rectangle(output, (x1, y1), (x2, y2), (255, 0, 0), 2)
        
        return output
    
    def zoom_to_region(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        zoom_factor: float = 2.0,
    ) -> np.ndarray:
        """Zoom into a specific region of the frame"""
        if cv2 is None:
            return frame
        
        x1, y1, x2, y2 = bbox
        
        # Calculate center
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        
        # Calculate zoom window size
        h, w = frame.shape[:2]
        zoom_w = int(w / zoom_factor)
        zoom_h = int(h / zoom_factor)
        
        # Calculate crop region (centered on detection)
        crop_x1 = max(0, cx - zoom_w // 2)
        crop_y1 = max(0, cy - zoom_h // 2)
        crop_x2 = min(w, crop_x1 + zoom_w)
        crop_y2 = min(h, crop_y1 + zoom_h)
        
        # Crop and resize
        cropped = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        zoomed = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
        
        return zoomed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return {
            "model_loaded": self._model_loaded,
            "total_processed": self._total_processed,
            "avg_processing_time_ms": round(self._avg_processing_time, 2),
            "model": cv_settings.yolo_model,
            "device": cv_settings.yolo_device,
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        return {
            "model_loaded": self._model_loaded,
            "status": "ready" if self._model_loaded else "not_loaded",
            **self.get_stats(),
        }

