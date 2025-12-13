"""
LLM Brain - OpenAI Integration for Vision Decision Making

The "brain" that analyzes scene descriptions and makes intelligent decisions
about what actions the operator should take.

Modes:
- AUTOMATIC: Decisions without human confirmation
- SEMI_AUTOMATIC: Brain suggests, operator confirms
- DIAGNOSTIC: Explains reasoning for decisions
"""

import json
import time
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import uuid

from ..cv_logger import cv_logger, LogLevel

# OpenAI client - will be initialized with API key from environment
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None


class BrainMode(str, Enum):
    """Brain operation mode"""
    AUTOMATIC = "automatic"
    SEMI_AUTOMATIC = "semi_automatic"
    DIAGNOSTIC = "diagnostic"


@dataclass
class BrainRequest:
    """Request to the LLM brain"""
    session_id: str
    scene_description: Dict[str, Any]
    mode: BrainMode = BrainMode.SEMI_AUTOMATIC
    additional_context: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "scene_description": self.scene_description,
            "mode": self.mode.value,
            "additional_context": self.additional_context,
        }


@dataclass
class BrainDecision:
    """Decision from the LLM brain"""
    decision_id: str
    decision_type: str  # next_step, final_result, clarification_needed, error
    actions: List[Dict[str, Any]] = field(default_factory=list)
    comments: str = ""
    confidence: float = 0.0
    tokens_used: int = 0
    latency_ms: float = 0.0
    raw_response: Optional[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if not self.decision_id:
            self.decision_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type,
            "actions": self.actions,
            "comments": self.comments,
            "confidence": self.confidence,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
        }


# System prompts for different modes
SYSTEM_PROMPTS = {
    BrainMode.AUTOMATIC: """You are an AI vision assistant helping digitize electronic components.
You analyze scenes from a camera feed showing electronic parts on a work table.

Your role:
1. Analyze YOLO detections and OCR results
2. Identify part numbers, serial numbers, and model information
3. Guide the operator with clear, concise instructions
4. Make decisions quickly and confidently

Response format (JSON):
{
    "decision_type": "next_step" | "final_result" | "clarification_needed",
    "actions": [
        {
            "type": "operator_instruction" | "mark_candidate_part_number" | "confirm_detection" | "request_repositioning" | "complete_task",
            "message": "instruction text",
            "value": "extracted value if applicable",
            "confidence": 0.0-1.0
        }
    ],
    "comments": "brief explanation",
    "confidence": 0.0-1.0
}

Be decisive and efficient. Only request repositioning if truly necessary.""",

    BrainMode.SEMI_AUTOMATIC: """You are an AI vision assistant helping digitize electronic components.
You work alongside a human operator, suggesting actions and waiting for confirmation.

Your role:
1. Analyze YOLO detections and OCR results
2. Suggest what the operator should do next
3. Present findings for operator verification
4. Be helpful but defer final decisions to the human

Response format (JSON):
{
    "decision_type": "next_step" | "final_result" | "clarification_needed",
    "actions": [
        {
            "type": "operator_instruction" | "mark_candidate_part_number" | "confirm_detection" | "request_repositioning" | "complete_task",
            "message": "instruction text",
            "value": "extracted value if applicable",
            "confidence": 0.0-1.0
        }
    ],
    "comments": "explanation of your reasoning",
    "confidence": 0.0-1.0
}

Always explain your reasoning. Present alternatives when uncertain.""",

    BrainMode.DIAGNOSTIC: """You are an AI vision assistant in diagnostic mode.
You explain your reasoning in detail to help operators understand the recognition process.

Your role:
1. Analyze YOLO detections and OCR results thoroughly
2. Explain what you see and why you interpret it that way
3. Discuss confidence levels and potential alternatives
4. Provide educational context about the recognition process

Response format (JSON):
{
    "decision_type": "next_step" | "final_result" | "clarification_needed",
    "actions": [
        {
            "type": "operator_instruction" | "mark_candidate_part_number" | "confirm_detection" | "request_repositioning" | "complete_task",
            "message": "detailed instruction with explanation",
            "value": "extracted value if applicable",
            "confidence": 0.0-1.0
        }
    ],
    "comments": "detailed explanation of reasoning, alternatives considered, and confidence factors",
    "confidence": 0.0-1.0
}

Be thorough in explanations. Help the operator learn.""",
}


class LLMBrain:
    """
    LLM Brain - The decision-making component
    
    Uses OpenAI GPT models to analyze vision data and make intelligent decisions.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Initialize LLM Brain
        
        Args:
            api_key: OpenAI API key (uses env OPENAI_API_KEY if not provided)
            model: OpenAI model to use (default: gpt-4o-mini for cost efficiency)
        """
        self._api_key = api_key
        self._model = model
        self._client: Optional[AsyncOpenAI] = None
        self._initialized = False
        self._mode = BrainMode.SEMI_AUTOMATIC
        
        # Statistics
        self._total_requests = 0
        self._total_tokens = 0
        self._total_errors = 0
        self._avg_latency_ms = 0.0
    
    async def initialize(self) -> bool:
        """Initialize the OpenAI client"""
        if not OPENAI_AVAILABLE:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                "OpenAI package not installed. Install with: pip install openai"
            )
            return False
        
        try:
            import os
            api_key = self._api_key or os.getenv("OPENAI_API_KEY")
            
            if not api_key:
                cv_logger._log(
                    LogLevel.ERROR, "BRAIN",
                    "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
                )
                return False
            
            self._client = AsyncOpenAI(api_key=api_key)
            self._initialized = True
            
            cv_logger._log(
                LogLevel.INFO, "BRAIN",
                f"LLM Brain initialized with model: {self._model}"
            )
            
            return True
            
        except Exception as e:
            cv_logger._log(
                LogLevel.ERROR, "BRAIN",
                f"Failed to initialize LLM Brain: {e}"
            )
            return False
    
    def set_mode(self, mode: BrainMode):
        """Set the brain operation mode"""
        self._mode = mode
        cv_logger._log(
            LogLevel.INFO, "BRAIN",
            f"Brain mode set to: {mode.value}"
        )
    
    async def analyze_scene(self, request: BrainRequest) -> BrainDecision:
        """
        Analyze a scene and make a decision
        
        Args:
            request: BrainRequest with scene description
            
        Returns:
            BrainDecision with actions and recommendations
        """
        if not self._initialized or not self._client:
            return BrainDecision(
                decision_id=str(uuid.uuid4()),
                decision_type="error",
                error="LLM Brain not initialized",
            )
        
        start_time = time.time()
        
        try:
            # Build the prompt
            system_prompt = SYSTEM_PROMPTS.get(request.mode or self._mode, SYSTEM_PROMPTS[BrainMode.SEMI_AUTOMATIC])
            
            user_message = self._build_user_message(request)
            
            cv_logger._log(
                LogLevel.DEBUG, "OPENAI",
                f"Sending request to OpenAI",
                payload={"session_id": request.session_id, "model": self._model}
            )
            
            # Call OpenAI API
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more consistent decisions
                max_tokens=1000,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            # Parse response
            raw_content = response.choices[0].message.content
            decision_data = json.loads(raw_content)
            
            decision = BrainDecision(
                decision_id=str(uuid.uuid4()),
                decision_type=decision_data.get("decision_type", "next_step"),
                actions=decision_data.get("actions", []),
                comments=decision_data.get("comments", ""),
                confidence=decision_data.get("confidence", 0.5),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                raw_response=raw_content,
            )
            
            # Update statistics
            self._total_requests += 1
            self._total_tokens += tokens_used
            self._avg_latency_ms = (
                (self._avg_latency_ms * (self._total_requests - 1) + latency_ms)
                / self._total_requests
            )
            
            cv_logger._log(
                LogLevel.INFO, "OPENAI",
                f"OpenAI response received",
                payload={
                    "session_id": request.session_id,
                    "decision_type": decision.decision_type,
                    "actions_count": len(decision.actions),
                    "tokens": tokens_used,
                    "latency_ms": round(latency_ms, 2),
                }
            )
            
            return decision
            
        except json.JSONDecodeError as e:
            self._total_errors += 1
            cv_logger._log(
                LogLevel.ERROR, "OPENAI",
                f"Failed to parse OpenAI response as JSON: {e}"
            )
            return BrainDecision(
                decision_id=str(uuid.uuid4()),
                decision_type="error",
                error=f"JSON parse error: {e}",
                latency_ms=(time.time() - start_time) * 1000,
            )
            
        except Exception as e:
            self._total_errors += 1
            cv_logger._log(
                LogLevel.ERROR, "OPENAI",
                f"OpenAI API error: {e}"
            )
            return BrainDecision(
                decision_id=str(uuid.uuid4()),
                decision_type="error",
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )
    
    def _build_user_message(self, request: BrainRequest) -> str:
        """Build the user message for the LLM"""
        scene = request.scene_description
        
        parts = []
        
        # Task context
        if "task_context" in scene:
            ctx = scene["task_context"]
            parts.append(f"## Task Context")
            parts.append(f"- Mode: {ctx.get('mode', 'general')}")
            if ctx.get("expected_object_type"):
                parts.append(f"- Expected object: {ctx['expected_object_type']}")
            if ctx.get("notes"):
                parts.append(f"- Notes: {ctx['notes']}")
            parts.append("")
        
        # Current frame data
        if "frame" in scene:
            frame = scene["frame"]
            parts.append(f"## Current Frame (#{frame.get('frame_id', 'N/A')})")
            
            # Detections
            detections = frame.get("detections", [])
            if detections:
                parts.append(f"\n### Detected Objects ({len(detections)}):")
                for i, det in enumerate(detections, 1):
                    conf = det.get("confidence", 0)
                    parts.append(
                        f"{i}. {det.get('class_name', 'unknown')} "
                        f"(confidence: {conf:.0%}, bbox: {det.get('bbox', {})})"
                    )
            else:
                parts.append("\n### Detected Objects: None")
            
            # OCR results
            ocr_results = frame.get("ocr_results", [])
            if ocr_results:
                parts.append(f"\n### OCR Results ({len(ocr_results)}):")
                for i, ocr in enumerate(ocr_results, 1):
                    conf = ocr.get("confidence", 0)
                    parts.append(
                        f'{i}. Text: "{ocr.get("cleaned_text", ocr.get("raw_text", ""))}" '
                        f"(confidence: {conf:.0%})"
                    )
            else:
                parts.append("\n### OCR Results: None")
            parts.append("")
        
        # Conversation history
        if "history" in scene and scene["history"]:
            parts.append("## Recent History:")
            for entry in scene["history"][-5:]:  # Last 5 entries
                role = entry.get("role", "unknown")
                msg = entry.get("message", "")
                parts.append(f"- [{role}] {msg}")
            parts.append("")
        
        # Additional context
        if request.additional_context:
            parts.append(f"## Additional Context:\n{request.additional_context}\n")
        
        parts.append("## Your Task:")
        parts.append("Analyze the scene and provide your decision in JSON format.")
        
        return "\n".join(parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get brain statistics"""
        return {
            "initialized": self._initialized,
            "model": self._model,
            "mode": self._mode.value,
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
            "total_errors": self._total_errors,
            "avg_latency_ms": round(self._avg_latency_ms, 2),
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Health check for the brain"""
        return {
            "status": "ready" if self._initialized else "not_initialized",
            **self.get_stats(),
        }

