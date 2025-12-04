"""
Computer Vision Module Configuration

This module contains all configuration settings for the CV pipeline including
camera settings, model paths, OCR settings, and Supabase configuration.
"""

from pydantic_settings import BaseSettings
from typing import Optional, List
from enum import Enum


class CameraMode(str, Enum):
    """Supported camera connection modes"""
    UVC = "uvc"  # USB Video Class (webcam mode)
    RTMP = "rtmp"  # RTMP streaming
    RTSP = "rtsp"  # RTSP streaming
    FILE = "file"  # File/video input for testing


class OCREngine(str, Enum):
    """Supported OCR engines"""
    EASYOCR = "easyocr"
    PADDLEOCR = "paddleocr"
    TESSERACT = "tesseract"


class CVSettings(BaseSettings):
    """Computer Vision module settings"""
    
    # Camera Settings
    camera_mode: CameraMode = CameraMode.UVC
    camera_device_id: int = 0  # UVC device ID
    camera_rtmp_url: Optional[str] = None
    camera_rtsp_url: Optional[str] = None
    camera_width: int = 1920
    camera_height: int = 1080
    camera_fps: int = 30
    
    # Stream Settings
    stream_quality: int = 80  # JPEG quality for streaming (1-100)
    stream_max_fps: int = 30
    stream_buffer_size: int = 5
    
    # YOLO Settings
    yolo_model: str = "yolov8n.pt"  # nano model for speed, can use yolov8s.pt, yolov8m.pt
    yolo_confidence: float = 0.5
    yolo_iou_threshold: float = 0.45
    yolo_device: str = "cpu"  # or "cuda" for GPU
    yolo_classes: Optional[List[int]] = None  # Filter specific classes
    
    # OCR Settings
    ocr_engine: OCREngine = OCREngine.EASYOCR
    ocr_languages: List[str] = ["en", "ru"]
    ocr_confidence_threshold: float = 0.3
    ocr_gpu: bool = False
    
    # Text Detection Settings
    text_detection_enabled: bool = True
    text_min_area: int = 100  # Minimum text region area in pixels
    text_padding: int = 10  # Padding around detected text regions
    
    # Processing Settings
    process_every_n_frames: int = 5  # Process every Nth frame for CV
    ocr_every_n_frames: int = 30  # Run OCR every Nth frame
    save_debug_frames: bool = False
    
    # Supabase Settings
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    supabase_bucket_crops: str = "camera_crops"
    supabase_bucket_debug: str = "camera_debug_frames"
    
    # Logging Settings
    log_level: str = "INFO"
    log_to_supabase: bool = True
    log_buffer_size: int = 100
    
    # Health Check Settings
    health_check_interval: int = 30  # seconds
    
    class Config:
        env_prefix = "CV_"
        env_file = ".env"


# Global settings instance
cv_settings = CVSettings()


# Supabase table names
TABLES = {
    "ocr_logs": "camera_ocr_logs",
    "logs": "camera_logs",
    "frames": "camera_frames",
}

# Log subsystems
SUBSYSTEMS = {
    "camera": "CAMERA",
    "stream": "STREAM",
    "cv": "CV",
    "ocr": "OCR",
    "supabase": "SUPABASE",
    "error": "ERROR",
    "system": "SYSTEM",
    # Brain layer subsystems
    "yolo": "YOLO",
    "brain": "BRAIN",
    "openai": "OPENAI",
    "orchestrator": "ORCHESTRATOR",
    "operator_ui": "OPERATOR_UI",
}

