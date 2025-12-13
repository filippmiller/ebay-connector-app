"""
Camera Service for DJI Osmo Pocket 3

Supports multiple connection modes:
- UVC (USB Video Class): Direct USB connection as webcam
- RTMP: Network streaming via RTMP protocol
- RTSP: Network streaming via RTSP protocol
- FILE: Video file input for testing

DJI Osmo Pocket 3 supports:
- UVC mode with 4K resolution (after firmware v02.00.06.01)
- RTMP streaming to platforms like YouTube
"""

import asyncio
import threading
import time
from typing import Optional, Tuple, Callable, List, Generator
from dataclasses import dataclass
from enum import Enum
from queue import Queue, Empty
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from .config import cv_settings, CameraMode
from .cv_logger import cv_logger, LogLevel


@dataclass
class CameraInfo:
    """Camera device information"""
    device_id: int
    name: str
    width: int
    height: int
    fps: float
    backend: str
    is_connected: bool = False


@dataclass
class Frame:
    """Video frame with metadata"""
    data: np.ndarray
    frame_number: int
    timestamp: float
    width: int
    height: int
    
    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.data.shape


class CameraState(str, Enum):
    """Camera connection state"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class CameraService:
    """
    Camera Service for video capture
    
    Features:
    - Multiple input sources (UVC, RTMP, RTSP, File)
    - Auto-reconnection on disconnect
    - Frame buffering for smooth streaming
    - FPS monitoring
    - Health checks
    """
    
    def __init__(self):
        if cv2 is None:
            raise ImportError("OpenCV (cv2) is required for CameraService. Install with: pip install opencv-python")
        
        self._capture: Optional[cv2.VideoCapture] = None
        self._state: CameraState = CameraState.DISCONNECTED
        self._frame_queue: Queue = Queue(maxsize=cv_settings.stream_buffer_size)
        self._frame_number: int = 0
        self._fps: float = 0.0
        self._last_fps_update: float = 0.0
        self._fps_frame_count: int = 0
        
        self._capture_thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()
        
        self._frame_callbacks: List[Callable[[Frame], None]] = []
        self._camera_info: Optional[CameraInfo] = None
        
        # Reconnection settings
        self._max_reconnect_attempts: int = 5
        self._reconnect_delay: float = 2.0
        self._reconnect_attempts: int = 0
    
    @property
    def state(self) -> CameraState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state in (CameraState.CONNECTED, CameraState.STREAMING)
    
    @property
    def fps(self) -> float:
        return self._fps
    
    @property
    def frame_number(self) -> int:
        return self._frame_number
    
    @property
    def camera_info(self) -> Optional[CameraInfo]:
        return self._camera_info
    
    def _set_state(self, state: CameraState):
        """Update camera state and log"""
        old_state = self._state
        self._state = state
        cv_logger.set_status("camera", state.value)
        cv_logger.camera(
            f"State changed: {old_state.value} -> {state.value}",
            level=LogLevel.DEBUG
        )
    
    def _build_capture_source(self) -> str | int:
        """Build capture source based on mode"""
        mode = cv_settings.camera_mode
        
        if mode == CameraMode.UVC:
            return cv_settings.camera_device_id
        elif mode == CameraMode.RTMP:
            if not cv_settings.camera_rtmp_url:
                raise ValueError("RTMP URL not configured (CV_CAMERA_RTMP_URL)")
            return cv_settings.camera_rtmp_url
        elif mode == CameraMode.RTSP:
            if not cv_settings.camera_rtsp_url:
                raise ValueError("RTSP URL not configured (CV_CAMERA_RTSP_URL)")
            return cv_settings.camera_rtsp_url
        elif mode == CameraMode.FILE:
            # For testing with video files
            return cv_settings.camera_rtmp_url or "test_video.mp4"
        else:
            raise ValueError(f"Unsupported camera mode: {mode}")
    
    def _get_backend(self) -> int:
        """Get appropriate OpenCV backend"""
        mode = cv_settings.camera_mode
        
        if mode == CameraMode.UVC:
            # Use DirectShow on Windows, V4L2 on Linux
            import platform
            if platform.system() == "Windows":
                return cv2.CAP_DSHOW
            else:
                return cv2.CAP_V4L2
        else:
            # Use FFmpeg for network streams
            return cv2.CAP_FFMPEG
    
    def list_cameras(self) -> List[CameraInfo]:
        """List available UVC cameras"""
        cameras = []
        
        for i in range(10):  # Check first 10 indices
            cap = cv2.VideoCapture(i, self._get_backend())
            if cap.isOpened():
                cameras.append(CameraInfo(
                    device_id=i,
                    name=f"Camera {i}",
                    width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    fps=cap.get(cv2.CAP_PROP_FPS),
                    backend=str(self._get_backend()),
                    is_connected=True,
                ))
                cap.release()
        
        cv_logger.camera(f"Found {len(cameras)} cameras", payload={"cameras": [c.device_id for c in cameras]})
        return cameras
    
    def connect(self) -> bool:
        """Connect to camera"""
        if self._state == CameraState.CONNECTED or self._state == CameraState.STREAMING:
            cv_logger.camera("Already connected", level=LogLevel.WARNING)
            return True
        
        self._set_state(CameraState.CONNECTING)
        
        try:
            source = self._build_capture_source()
            backend = self._get_backend()
            
            cv_logger.camera(
                f"Connecting to camera",
                payload={"source": str(source), "mode": cv_settings.camera_mode.value}
            )
            
            self._capture = cv2.VideoCapture(source, backend)
            
            if not self._capture.isOpened():
                raise ConnectionError(f"Failed to open camera: {source}")
            
            # Configure camera
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, cv_settings.camera_width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, cv_settings.camera_height)
            self._capture.set(cv2.CAP_PROP_FPS, cv_settings.camera_fps)
            
            # Get actual settings
            actual_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self._capture.get(cv2.CAP_PROP_FPS)
            
            self._camera_info = CameraInfo(
                device_id=cv_settings.camera_device_id if isinstance(source, int) else -1,
                name=str(source),
                width=actual_width,
                height=actual_height,
                fps=actual_fps,
                backend=str(backend),
                is_connected=True,
            )
            
            self._set_state(CameraState.CONNECTED)
            self._reconnect_attempts = 0
            
            cv_logger.camera(
                "Camera connected successfully",
                payload={
                    "width": actual_width,
                    "height": actual_height,
                    "fps": actual_fps,
                }
            )
            
            return True
            
        except Exception as e:
            self._set_state(CameraState.ERROR)
            cv_logger.camera(f"Connection failed: {e}", level=LogLevel.ERROR)
            return False
    
    def disconnect(self):
        """Disconnect from camera"""
        self._running = False
        
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
        
        if self._capture:
            self._capture.release()
            self._capture = None
        
        self._set_state(CameraState.DISCONNECTED)
        self._camera_info = None
        
        cv_logger.camera("Camera disconnected")
    
    def _capture_loop(self):
        """Main capture loop running in separate thread"""
        cv_logger.camera("Capture loop started")
        self._set_state(CameraState.STREAMING)
        
        while self._running:
            try:
                if not self._capture or not self._capture.isOpened():
                    self._handle_disconnect()
                    continue
                
                ret, frame_data = self._capture.read()
                
                if not ret or frame_data is None:
                    cv_logger.camera("Failed to read frame", level=LogLevel.WARNING)
                    self._handle_disconnect()
                    continue
                
                self._frame_number += 1
                current_time = time.time()
                
                # Create frame object
                frame = Frame(
                    data=frame_data,
                    frame_number=self._frame_number,
                    timestamp=current_time,
                    width=frame_data.shape[1],
                    height=frame_data.shape[0],
                )
                
                # Update FPS
                self._fps_frame_count += 1
                if current_time - self._last_fps_update >= 1.0:
                    self._fps = self._fps_frame_count / (current_time - self._last_fps_update)
                    cv_logger.update_fps(self._fps)
                    self._fps_frame_count = 0
                    self._last_fps_update = current_time
                
                # Add to queue (non-blocking)
                try:
                    if self._frame_queue.full():
                        self._frame_queue.get_nowait()  # Drop oldest frame
                    self._frame_queue.put_nowait(frame)
                except Empty:
                    pass
                
                # Call frame callbacks
                for callback in self._frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as e:
                        cv_logger.camera(f"Frame callback error: {e}", level=LogLevel.ERROR)
                
            except Exception as e:
                cv_logger.camera(f"Capture loop error: {e}", level=LogLevel.ERROR)
                self._handle_disconnect()
        
        cv_logger.camera("Capture loop stopped")
    
    def _handle_disconnect(self):
        """Handle camera disconnection with reconnection logic"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            self._set_state(CameraState.ERROR)
            cv_logger.camera(
                f"Max reconnection attempts ({self._max_reconnect_attempts}) reached",
                level=LogLevel.ERROR
            )
            self._running = False
            return
        
        self._set_state(CameraState.RECONNECTING)
        self._reconnect_attempts += 1
        
        cv_logger.camera(
            f"Attempting reconnection ({self._reconnect_attempts}/{self._max_reconnect_attempts})",
            level=LogLevel.WARNING
        )
        
        time.sleep(self._reconnect_delay)
        
        if self._capture:
            self._capture.release()
        
        if self.connect():
            self._set_state(CameraState.STREAMING)
    
    def start_streaming(self) -> bool:
        """Start video capture in background thread"""
        if not self.is_connected:
            if not self.connect():
                return False
        
        if self._running:
            cv_logger.camera("Already streaming", level=LogLevel.WARNING)
            return True
        
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        
        cv_logger.camera("Streaming started")
        return True
    
    def stop_streaming(self):
        """Stop video capture"""
        self._running = False
        
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
        
        self._set_state(CameraState.CONNECTED)
        cv_logger.camera("Streaming stopped")
    
    def get_frame(self, timeout: float = 0.1) -> Optional[Frame]:
        """Get latest frame from queue"""
        try:
            return self._frame_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def get_latest_frame(self) -> Optional[Frame]:
        """Get the most recent frame, discarding older ones"""
        frame = None
        while True:
            try:
                frame = self._frame_queue.get_nowait()
            except Empty:
                break
        return frame
    
    def register_frame_callback(self, callback: Callable[[Frame], None]):
        """Register callback for each captured frame"""
        self._frame_callbacks.append(callback)
    
    def unregister_frame_callback(self, callback: Callable[[Frame], None]):
        """Unregister frame callback"""
        if callback in self._frame_callbacks:
            self._frame_callbacks.remove(callback)
    
    def frame_generator(self) -> Generator[Frame, None, None]:
        """Generator yielding frames continuously"""
        while self._running:
            frame = self.get_frame()
            if frame:
                yield frame
    
    async def frame_generator_async(self) -> Generator[Frame, None, None]:
        """Async generator yielding frames"""
        while self._running:
            frame = self.get_frame(timeout=0.01)
            if frame:
                yield frame
            else:
                await asyncio.sleep(0.01)
    
    def health_check(self) -> dict:
        """Perform health check"""
        return {
            "connected": self.is_connected,
            "state": self._state.value,
            "fps": self._fps,
            "frame_number": self._frame_number,
            "queue_size": self._frame_queue.qsize(),
            "camera_info": {
                "width": self._camera_info.width if self._camera_info else None,
                "height": self._camera_info.height if self._camera_info else None,
                "fps": self._camera_info.fps if self._camera_info else None,
            } if self._camera_info else None,
        }
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

