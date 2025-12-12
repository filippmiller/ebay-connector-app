"""
Operator Guidance Service

WebSocket service for real-time communication with the operator UI.
Sends instructions from the brain and receives operator responses.
"""

import asyncio
import json
import uuid
from typing import Optional, Dict, Any, Set, Callable
from datetime import datetime, timezone
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

from ..cv_logger import cv_logger, LogLevel
from .brain_models import OperatorEventType
from .vision_brain_orchestrator import VisionBrainOrchestrator, SessionState


@dataclass
class OperatorClient:
    """Connected operator client"""
    websocket: WebSocket
    client_id: str
    session_id: Optional[str] = None
    connected_at: str = ""
    
    def __post_init__(self):
        if not self.connected_at:
            self.connected_at = datetime.now(timezone.utc).isoformat()


class OperatorGuidanceService:
    """
    WebSocket service for operator guidance
    
    Messages FROM server TO client:
    - brain_instruction: Instructions from the brain
    - state_change: Session state changes
    - history_update: New history entries
    - session_started: New session started
    - session_ended: Session ended
    - error: Error messages
    
    Messages FROM client TO server:
    - operator_event: Operator actions (confirm, reject, etc.)
    - manual_input: Manual text input from operator
    - session_control: Start/stop/pause session
    """
    
    def __init__(self, orchestrator: VisionBrainOrchestrator):
        self._orchestrator = orchestrator
        self._clients: Dict[str, OperatorClient] = {}
        
        # Register callbacks with orchestrator
        self._orchestrator.set_instruction_callback(self._on_brain_instruction)
        self._orchestrator.set_state_change_callback(self._on_state_change)
    
    async def connect(self, websocket: WebSocket) -> str:
        """Accept new WebSocket connection"""
        await websocket.accept()
        
        client_id = str(uuid.uuid4())
        client = OperatorClient(
            websocket=websocket,
            client_id=client_id,
        )
        
        self._clients[client_id] = client
        
        cv_logger._log(
            LogLevel.INFO, "OPERATOR_UI",
            f"Operator connected: {client_id}"
        )
        
        # Send initial state
        await self._send_to_client(client_id, {
            "type": "connected",
            "client_id": client_id,
            "state": self._orchestrator.get_current_state(),
            "history": self._orchestrator.get_history(),
        })
        
        return client_id
    
    async def disconnect(self, client_id: str):
        """Handle client disconnection"""
        if client_id in self._clients:
            del self._clients[client_id]
            
            cv_logger._log(
                LogLevel.INFO, "OPERATOR_UI",
                f"Operator disconnected: {client_id}"
            )
    
    async def handle_message(self, client_id: str, message: Dict[str, Any]):
        """Handle incoming message from client"""
        msg_type = message.get("type")
        
        cv_logger._log(
            LogLevel.DEBUG, "OPERATOR_UI",
            f"Received message: {msg_type}",
            payload={"client_id": client_id}
        )
        
        try:
            if msg_type == "operator_event":
                await self._handle_operator_event(client_id, message)
                
            elif msg_type == "manual_input":
                await self._handle_manual_input(client_id, message)
                
            elif msg_type == "session_control":
                await self._handle_session_control(client_id, message)
                
            elif msg_type == "ping":
                await self._send_to_client(client_id, {"type": "pong"})
                
            elif msg_type == "get_state":
                await self._send_to_client(client_id, {
                    "type": "state",
                    "state": self._orchestrator.get_current_state(),
                })
                
            elif msg_type == "get_history":
                await self._send_to_client(client_id, {
                    "type": "history",
                    "history": self._orchestrator.get_history(),
                })
                
            else:
                cv_logger._log(
                    LogLevel.WARNING, "OPERATOR_UI",
                    f"Unknown message type: {msg_type}"
                )
                
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "OPERATOR_UI",
                f"Error handling message: {e}"
            )
            await self._send_to_client(client_id, {
                "type": "error",
                "message": str(e),
            })
    
    async def _handle_operator_event(self, client_id: str, message: Dict):
        """Handle operator event (confirm, reject, etc.)"""
        event_type_str = message.get("event_type", "action_confirmed")
        comment = message.get("comment")
        payload = message.get("payload", {})
        
        try:
            event_type = OperatorEventType(event_type_str)
        except ValueError:
            event_type = OperatorEventType.ACTION_CONFIRMED
        
        await self._orchestrator.handle_operator_event(
            event_type=event_type,
            payload=payload,
            comment=comment,
        )
        
        # Broadcast state update to all clients
        await self._broadcast({
            "type": "state_change",
            "state": self._orchestrator.get_current_state(),
        })
    
    async def _handle_manual_input(self, client_id: str, message: Dict):
        """Handle manual text input from operator"""
        text = message.get("text", "")
        field = message.get("field", "part_number")
        
        await self._orchestrator.handle_operator_event(
            event_type=OperatorEventType.MANUAL_INPUT,
            payload={"field": field, "value": text},
            comment=f"Manual input for {field}: {text}",
        )
    
    async def _handle_session_control(self, client_id: str, message: Dict):
        """Handle session control commands"""
        action = message.get("action")
        
        if action == "start":
            mode = message.get("mode", "part_number_extraction")
            expected_object = message.get("expected_object")
            notes = message.get("notes")
            
            from .brain_models import TaskMode
            try:
                task_mode = TaskMode(mode)
            except ValueError:
                task_mode = TaskMode.PART_NUMBER_EXTRACTION
            
            session_id = await self._orchestrator.start_session(
                task_mode=task_mode,
                expected_object_type=expected_object,
                notes=notes,
            )
            
            # Update client's session
            if client_id in self._clients:
                self._clients[client_id].session_id = session_id
            
            await self._broadcast({
                "type": "session_started",
                "session_id": session_id,
                "state": self._orchestrator.get_current_state(),
            })
            
        elif action == "stop":
            await self._orchestrator.end_session()
            
            await self._broadcast({
                "type": "session_ended",
                "state": self._orchestrator.get_current_state(),
            })
            
        elif action == "pause":
            self._orchestrator.pause_session()
            
            await self._broadcast({
                "type": "state_change",
                "state": self._orchestrator.get_current_state(),
            })
            
        elif action == "resume":
            self._orchestrator.resume_session()
            
            await self._broadcast({
                "type": "state_change",
                "state": self._orchestrator.get_current_state(),
            })
    
    # ==================== Callbacks from Orchestrator ====================
    
    def _on_brain_instruction(self, instruction: Dict):
        """Called when brain produces an instruction"""
        # Run in asyncio loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast(instruction))
        except RuntimeError:
            pass
    
    def _on_state_change(self, state: SessionState):
        """Called when session state changes"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({
                "type": "state_change",
                "session_state": state.value,
                "state": self._orchestrator.get_current_state(),
            }))
        except RuntimeError:
            pass
    
    # ==================== Sending ====================
    
    async def _send_to_client(self, client_id: str, message: Dict):
        """Send message to specific client"""
        if client_id not in self._clients:
            return
        
        try:
            await self._clients[client_id].websocket.send_json(message)
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "OPERATOR_UI",
                f"Failed to send to client {client_id}: {e}"
            )
            await self.disconnect(client_id)
    
    async def _broadcast(self, message: Dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        
        for client_id, client in self._clients.items():
            try:
                await client.websocket.send_json(message)
            except Exception:
                disconnected.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)
    
    # ==================== Status ====================
    
    def get_connected_clients(self) -> int:
        """Get number of connected clients"""
        return len(self._clients)
    
    def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {
            "status": "active" if self._clients else "idle",
            "connected_clients": len(self._clients),
            "clients": [
                {
                    "client_id": c.client_id,
                    "session_id": c.session_id,
                    "connected_at": c.connected_at,
                }
                for c in self._clients.values()
            ],
        }

