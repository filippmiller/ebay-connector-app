"""
Stream Router - WebSocket Video Streaming

Handles real-time video streaming to web clients via WebSocket.
Supports MJPEG streaming with optional CV overlay rendering.
"""

import asyncio
import time
import json
from typing import Optional, Set, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import threading
from queue import Queue, Empty
import base64

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from fastapi import WebSocket, WebSocketDisconnect

from .config import cv_settings
from .cv_logger import cv_logger, LogLevel
from .camera_service import CameraService, Frame
from .vision_service import VisionService, VisionResult


class StreamMode(str, Enum):
    """Video stream modes"""
    RAW = "raw"  # Raw video frames
    ANNOTATED = "annotated"  # With CV detection overlays
    BOTH = "both"  # Side by side


@dataclass
class StreamClient:
    """WebSocket client connection"""
    websocket: WebSocket
    client_id: str
    mode: StreamMode = StreamMode.RAW
    connected_at: float = 0.0
    frames_sent: int = 0
    last_frame_time: float = 0.0
    
    def __post_init__(self):
        if self.connected_at == 0.0:
            self.connected_at = time.time()


class StreamRouter:
    """
    WebSocket Video Stream Router
    
    Features:
    - Multiple client support
    - Configurable stream quality
    - FPS limiting
    - CV annotation overlay
    - Real-time metrics broadcasting
    """
    
    def __init__(
        self,
        camera_service: CameraService,
        vision_service: Optional[VisionService] = None,
    ):
        self._camera = camera_service
        self._vision = vision_service
        
        self._clients: Dict[str, StreamClient] = {}
        self._lock = threading.Lock()
        self._running: bool = False
        
        self._broadcast_task: Optional[asyncio.Task] = None
        self._last_vision_result: Optional[VisionResult] = None
        
        # Performance tracking
        self._frames_broadcast: int = 0
        self._start_time: float = 0.0
    
    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        mode: StreamMode = StreamMode.RAW,
    ) -> bool:
        """Accept new WebSocket connection"""
        try:
            await websocket.accept()
            
            client = StreamClient(
                websocket=websocket,
                client_id=client_id,
                mode=mode,
            )
            
            with self._lock:
                self._clients[client_id] = client
            
            cv_logger.stream(
                f"Client connected: {client_id}",
                payload={"mode": mode.value, "total_clients": len(self._clients)}
            )
            
            # Send initial state
            await self._send_state(client)
            
            return True
            
        except Exception as e:
            cv_logger.stream(f"Connection failed for {client_id}: {e}", level=LogLevel.ERROR)
            return False
    
    async def disconnect(self, client_id: str):
        """Handle client disconnection"""
        with self._lock:
            if client_id in self._clients:
                client = self._clients.pop(client_id)
                cv_logger.stream(
                    f"Client disconnected: {client_id}",
                    payload={
                        "frames_sent": client.frames_sent,
                        "duration": time.time() - client.connected_at,
                    }
                )
    
    async def _send_state(self, client: StreamClient):
        """Send initial state to client"""
        state = {
            "type": "state",
            "camera": self._camera.health_check(),
            "vision": self._vision.health_check() if self._vision else None,
            "stream": {
                "mode": client.mode.value,
                "quality": cv_settings.stream_quality,
                "max_fps": cv_settings.stream_max_fps,
            },
        }
        await client.websocket.send_json(state)
    
    async def broadcast_frame(self, frame: Frame, vision_result: Optional[VisionResult] = None):
        """Broadcast frame to all connected clients"""
        if not self._clients or cv2 is None:
            return
        
        self._last_vision_result = vision_result
        
        # Prepare frames for different modes
        frames_cache: Dict[StreamMode, bytes] = {}
        
        with self._lock:
            clients = list(self._clients.values())
        
        for client in clients:
            try:
                # Check frame rate limiting
                current_time = time.time()
                min_interval = 1.0 / cv_settings.stream_max_fps
                if current_time - client.last_frame_time < min_interval:
                    continue
                
                # Get or create frame for this mode
                if client.mode not in frames_cache:
                    frames_cache[client.mode] = self._encode_frame(
                        frame, vision_result, client.mode
                    )
                
                frame_data = frames_cache[client.mode]
                
                if frame_data:
                    # Send as binary (more efficient) or base64
                    message = {
                        "type": "frame",
                        "frame_number": frame.frame_number,
                        "timestamp": frame.timestamp,
                        "width": frame.width,
                        "height": frame.height,
                        "data": base64.b64encode(frame_data).decode('utf-8'),
                    }
                    
                    if vision_result:
                        message["detections"] = len(vision_result.detections)
                        message["text_regions"] = len(vision_result.text_regions)
                    
                    await client.websocket.send_json(message)
                    
                    client.frames_sent += 1
                    client.last_frame_time = current_time
                    self._frames_broadcast += 1
                    
            except WebSocketDisconnect:
                await self.disconnect(client.client_id)
            except Exception as e:
                cv_logger.stream(
                    f"Failed to send frame to {client.client_id}: {e}",
                    level=LogLevel.WARNING
                )
    
    def _encode_frame(
        self,
        frame: Frame,
        vision_result: Optional[VisionResult],
        mode: StreamMode,
    ) -> Optional[bytes]:
        """Encode frame for streaming"""
        if cv2 is None:
            return None
        
        try:
            output = frame.data
            
            # Add annotations if requested
            if mode in (StreamMode.ANNOTATED, StreamMode.BOTH) and vision_result and self._vision:
                output = self._vision.draw_detections(output, vision_result)
            
            # Add FPS overlay
            fps_text = f"FPS: {self._camera.fps:.1f}"
            cv2.putText(
                output, fps_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
            )
            
            # Encode to JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, cv_settings.stream_quality]
            _, buffer = cv2.imencode('.jpg', output, encode_params)
            
            return buffer.tobytes()
            
        except Exception as e:
            cv_logger.stream(f"Frame encoding error: {e}", level=LogLevel.ERROR)
            return None
    
    async def broadcast_message(self, message: Dict[str, Any]):
        """Broadcast arbitrary message to all clients"""
        with self._lock:
            clients = list(self._clients.values())
        
        for client in clients:
            try:
                await client.websocket.send_json(message)
            except WebSocketDisconnect:
                await self.disconnect(client.client_id)
            except Exception:
                pass
    
    async def handle_client_message(self, client_id: str, message: Dict[str, Any]):
        """Handle incoming client message"""
        msg_type = message.get("type")
        
        if msg_type == "set_mode":
            mode = StreamMode(message.get("mode", "raw"))
            with self._lock:
                if client_id in self._clients:
                    self._clients[client_id].mode = mode
            cv_logger.stream(f"Client {client_id} changed mode to {mode.value}")
        
        elif msg_type == "ping":
            client = self._clients.get(client_id)
            if client:
                await client.websocket.send_json({"type": "pong", "timestamp": time.time()})
        
        elif msg_type == "get_state":
            client = self._clients.get(client_id)
            if client:
                await self._send_state(client)
    
    async def start_broadcast_loop(self):
        """Start continuous frame broadcast loop"""
        self._running = True
        self._start_time = time.time()
        
        cv_logger.stream("Broadcast loop started")
        
        frame_counter = 0
        
        while self._running:
            try:
                frame = self._camera.get_frame(timeout=0.1)
                
                if frame:
                    frame_counter += 1
                    vision_result = None
                    
                    # Run CV processing periodically
                    if (
                        self._vision and
                        self._vision._model_loaded and
                        frame_counter % cv_settings.process_every_n_frames == 0
                    ):
                        vision_result = self._vision.process_frame(frame)
                    
                    await self.broadcast_frame(frame, vision_result)
                else:
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                cv_logger.stream(f"Broadcast loop error: {e}", level=LogLevel.ERROR)
                await asyncio.sleep(0.1)
        
        cv_logger.stream("Broadcast loop stopped")
    
    def stop_broadcast_loop(self):
        """Stop broadcast loop"""
        self._running = False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""
        uptime = time.time() - self._start_time if self._start_time else 0
        avg_fps = self._frames_broadcast / uptime if uptime > 0 else 0
        
        return {
            "active_clients": len(self._clients),
            "frames_broadcast": self._frames_broadcast,
            "uptime_seconds": round(uptime, 1),
            "avg_fps": round(avg_fps, 1),
            "clients": [
                {
                    "client_id": c.client_id,
                    "mode": c.mode.value,
                    "frames_sent": c.frames_sent,
                    "connected_seconds": round(time.time() - c.connected_at, 1),
                }
                for c in self._clients.values()
            ],
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        return {
            "running": self._running,
            "status": "streaming" if self._running and self._clients else "idle",
            **self.get_stats(),
        }


class LogStreamRouter:
    """
    WebSocket Log Stream Router
    
    Broadcasts logs to connected debug console clients in real-time.
    """
    
    def __init__(self):
        self._clients: Dict[str, WebSocket] = {}
        self._lock = threading.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept new log stream connection"""
        await websocket.accept()
        
        with self._lock:
            self._clients[client_id] = websocket
        
        cv_logger.stream(f"Log client connected: {client_id}")
    
    async def disconnect(self, client_id: str):
        """Handle disconnection"""
        with self._lock:
            self._clients.pop(client_id, None)
        cv_logger.stream(f"Log client disconnected: {client_id}")
    
    async def broadcast_log(self, log_entry: Dict[str, Any]):
        """Broadcast log entry to all clients"""
        with self._lock:
            clients = list(self._clients.items())
        
        for client_id, ws in clients:
            try:
                await ws.send_json(log_entry)
            except:
                await self.disconnect(client_id)
    
    def get_callback(self) -> Callable:
        """Get callback for CVLogger registration"""
        async def callback(log_entry: Dict[str, Any]):
            await self.broadcast_log(log_entry)
        return callback

