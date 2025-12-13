# Computer Vision Module for DJI Osmo Pocket 3
# This module provides real-time video streaming, object detection, and OCR capabilities
#
# Key Features:
# - Camera capture from DJI Osmo Pocket 3 (UVC/RTMP/RTSP)
# - YOLOv8 real-time object detection
# - Multi-engine OCR (EasyOCR, PaddleOCR, Tesseract)
# - WebSocket video streaming
# - Supabase persistence (no local storage)
# - Structured logging with loguru

from .config import cv_settings, CVSettings, CameraMode, OCREngine
from .cv_logger import CVLogger, cv_logger, LogLevel
from .camera_service import CameraService, CameraState, Frame
from .vision_service import VisionService, Detection, VisionResult
from .ocr_service import OCRService, OCRResult, OCRBatchResult
from .supabase_writer import SupabaseWriter, OCRLogEntry
from .stream_router import StreamRouter, LogStreamRouter, StreamMode
from .cv_pipeline import CVPipeline, get_pipeline, PipelineState

__all__ = [
    # Config
    "cv_settings",
    "CVSettings",
    "CameraMode",
    "OCREngine",
    # Logger
    "CVLogger",
    "cv_logger",
    "LogLevel",
    # Camera
    "CameraService",
    "CameraState",
    "Frame",
    # Vision
    "VisionService",
    "Detection",
    "VisionResult",
    # OCR
    "OCRService",
    "OCRResult",
    "OCRBatchResult",
    # Storage
    "SupabaseWriter",
    "OCRLogEntry",
    # Streaming
    "StreamRouter",
    "LogStreamRouter",
    "StreamMode",
    # Pipeline
    "CVPipeline",
    "get_pipeline",
    "PipelineState",
]

