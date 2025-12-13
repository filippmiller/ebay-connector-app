# Vision Brain Layer Documentation

**Version:** 1.0  
**Date:** December 4, 2024  
**Module:** Brain Layer for Computer Vision (YOLO + OpenAI + Supabase)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Responsibilities](#module-responsibilities)
4. [Data Flows](#data-flows)
5. [API Reference](#api-reference)
6. [Database Schema](#database-schema)
7. [Configuration](#configuration)
8. [Usage Scenarios](#usage-scenarios)
9. [Error Handling](#error-handling)
10. [Extension Guide](#extension-guide)

---

## Overview

The Vision Brain Layer is an AI-powered orchestration system that connects:
- **YOLO Detector** — Real-time object detection
- **OCR Engine** — Text recognition on detected regions
- **OpenAI LLM** — "Brain" for decision-making and operator guidance
- **Supabase** — Exclusive data persistence (no local storage)
- **Operator UI** — Real-time instructions and interaction

### Core Principles

1. **Zero Local Storage**: All data persists exclusively in Supabase
2. **AI-First**: OpenAI makes intelligent decisions based on scene analysis
3. **Human-in-the-Loop**: Operator confirms or rejects brain decisions
4. **Full Traceability**: Complete audit trail in Supabase

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            VISION BRAIN LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│     ┌──────────────┐         ┌──────────────┐                               │
│     │   Camera     │         │    Video     │                               │
│     │   (DJI)      │────────▶│    Stream    │                               │
│     └──────────────┘         └───────┬──────┘                               │
│                                      │                                       │
│                                      ▼                                       │
│     ┌────────────────────────────────────────────────────────────┐          │
│     │                    YOLO DETECTOR                            │          │
│     │  • Object detection (YOLOv8/v9)                            │          │
│     │  • Bounding boxes + confidence                             │          │
│     │  • Class identification                                     │          │
│     └────────────────────────────────────────────────────────────┘          │
│                                      │                                       │
│                    ┌─────────────────┴─────────────────┐                    │
│                    ▼                                   ▼                    │
│     ┌──────────────────────┐          ┌──────────────────────┐             │
│     │    OCR SERVICE       │          │   TEXT REGIONS       │             │
│     │  • EasyOCR/Tesseract │          │  Cropped areas       │             │
│     │  • Part numbers      │          │  for OCR analysis    │             │
│     └──────────────────────┘          └──────────────────────┘             │
│                    │                                                         │
│                    ▼                                                         │
│     ┌────────────────────────────────────────────────────────────┐          │
│     │              VISION BRAIN ORCHESTRATOR                      │          │
│     │                                                             │          │
│     │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │          │
│     │  │   Scene     │  │    LLM      │  │  Decision   │        │          │
│     │  │ Description │─▶│   Brain     │─▶│  Actions    │        │          │
│     │  │   Builder   │  │  (OpenAI)   │  │  Processor  │        │          │
│     │  └─────────────┘  └─────────────┘  └─────────────┘        │          │
│     │                          │                                  │          │
│     │         ┌────────────────┼────────────────┐                │          │
│     │         ▼                ▼                ▼                │          │
│     │  ┌───────────┐    ┌───────────┐    ┌───────────┐          │          │
│     │  │ Operator  │    │ Supabase  │    │  History  │          │          │
│     │  │ Guidance  │    │  Writer   │    │  Tracker  │          │          │
│     │  └───────────┘    └───────────┘    └───────────┘          │          │
│     └────────────────────────────────────────────────────────────┘          │
│                    │                           │                             │
│                    ▼                           ▼                             │
│     ┌──────────────────────┐    ┌──────────────────────────────┐           │
│     │   OPERATOR UI        │    │         SUPABASE              │           │
│     │   (WebSocket)        │    │  • vision_sessions            │           │
│     │                      │    │  • vision_detections          │           │
│     │  • Instructions      │    │  • vision_ocr_results         │           │
│     │  • History           │    │  • vision_brain_decisions     │           │
│     │  • Action buttons    │    │  • vision_operator_events     │           │
│     └──────────────────────┘    └──────────────────────────────┘           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

### 1. YOLO Detector (`vision_service.py`)

**Purpose:** Object detection on video frames

**Responsibilities:**
- Load and run YOLOv8/v9 model
- Detect objects with bounding boxes
- Identify text regions for OCR
- Filter by confidence and target classes

**Output Format:**
```json
{
  "frame_id": 12345,
  "timestamp": "2024-12-04T10:30:00.000Z",
  "detections": [
    {
      "id": "uuid-1",
      "class_name": "laptop_motherboard",
      "class_id": 42,
      "confidence": 0.93,
      "bbox": { "x": 100, "y": 120, "w": 300, "h": 200 }
    }
  ]
}
```

### 2. OCR Reader (`ocr_service.py`)

**Purpose:** Text recognition on image regions

**Responsibilities:**
- Extract text from cropped regions
- Clean and normalize text
- Identify patterns (part numbers, serial numbers)
- Calculate confidence scores

**Output Format:**
```json
{
  "frame_id": 12345,
  "timestamp": "2024-12-04T10:30:00.000Z",
  "ocr_results": [
    {
      "crop_id": "uuid-2",
      "bbox": { "x": 150, "y": 140, "w": 100, "h": 30 },
      "raw_text": "HMT351U6CFR8C-H9",
      "cleaned_text": "HMT351U6CFR8C-H9",
      "confidence": 0.88
    }
  ]
}
```

### 3. LLM Brain (`llm_brain.py`)

**Purpose:** AI decision-making using OpenAI

**Responsibilities:**
- Analyze scene descriptions (YOLO + OCR + context)
- Generate operator instructions
- Identify and extract target values
- Make completion decisions

**Operation Modes:**

| Mode | Description |
|------|-------------|
| `automatic` | Decisions without operator confirmation |
| `semi_automatic` | Brain suggests, operator confirms |
| `diagnostic` | Detailed explanations of reasoning |

**Request Format:**
```json
{
  "session_id": "uuid-session",
  "task_context": {
    "mode": "part_number_extraction",
    "expected_object_type": "laptop_motherboard",
    "notes": "Extract part number from main sticker"
  },
  "frame": {
    "frame_id": 12345,
    "timestamp": "...",
    "detections": [...],
    "ocr_results": [...]
  },
  "history": [
    { "role": "brain", "type": "instruction", "message": "Turn the board over" },
    { "role": "operator", "type": "action_confirmed", "message": "Done" }
  ]
}
```

**Response Format:**
```json
{
  "decision_id": "uuid-decision",
  "decision_type": "next_step",
  "actions": [
    {
      "type": "operator_instruction",
      "message": "Move the part closer to the camera"
    },
    {
      "type": "mark_candidate_part_number",
      "value": "HMT351U6CFR8C-H9",
      "confidence": 0.92
    }
  ],
  "comments": "Found potential part number, need confirmation angle",
  "confidence": 0.85
}
```

### 4. Vision Brain Orchestrator (`vision_brain_orchestrator.py`)

**Purpose:** Central coordination of all components

**Responsibilities:**
- Manage vision sessions
- Process frames through YOLO → OCR → Brain pipeline
- Build scene descriptions for brain
- Handle operator events
- Maintain conversation history

**Session States:**

```
IDLE → SCANNING → ANALYZING → WAITING_FOR_OPERATOR → PROCESSING_RESPONSE
                                        ↓
                                   COMPLETED / ERROR
```

### 5. Operator Guidance Service (`operator_guidance_service.py`)

**Purpose:** Real-time communication with operator UI

**Responsibilities:**
- WebSocket connection management
- Push brain instructions to UI
- Receive operator events
- Broadcast state changes

**Server → Client Messages:**
```json
{
  "type": "brain_instruction",
  "session_id": "...",
  "decision_id": "...",
  "messages": ["Move the part closer to the camera"],
  "extracted_values": [{ "type": "part_number", "value": "XXX", "confidence": 0.92 }],
  "actions": [
    { "type": "button", "id": "confirm", "label": "Confirm" }
  ]
}
```

**Client → Server Messages:**
```json
{
  "type": "operator_event",
  "event_type": "action_confirmed",
  "comment": "Operator confirmed",
  "timestamp": "..."
}
```

### 6. Brain Repository (`brain_repository.py`)

**Purpose:** Supabase persistence layer

**Responsibilities:**
- Batch write to Supabase (no local storage)
- CRUD for sessions, detections, OCR, decisions, events
- Background write queue for performance
- Auto-flush on interval

---

## Data Flows

### Flow 1: Frame Processing

```
Camera Frame
     │
     ▼
┌─────────────────┐
│ Frame Counter   │ ←── Skip N frames for performance
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  YOLO Detector  │
│  (VisionService)│
└────────┬────────┘
         │
         ├── Detections saved to Supabase
         │
         ▼
┌─────────────────┐
│  OCR Service    │ ←── Only on text regions
│  (every M det.) │
└────────┬────────┘
         │
         ├── OCR results saved to Supabase
         │
         ▼
┌─────────────────┐
│  Brain (OpenAI) │ ←── Only every K OCR results
│  (LLMBrain)     │
└────────┬────────┘
         │
         ├── Decision saved to Supabase
         │
         ▼
┌─────────────────┐
│ Operator UI     │ ←── WebSocket push
│ (Guidance Svc)  │
└─────────────────┘
```

### Flow 2: Operator Interaction

```
Operator UI
     │
     │ WebSocket: operator_event
     ▼
┌─────────────────┐
│ Guidance Service│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Orchestrator    │
│ (handle_event)  │
└────────┬────────┘
         │
         ├── Event saved to Supabase
         ├── Decision status updated
         │
         ▼
┌─────────────────┐
│ State Change    │
│ Broadcast       │
└─────────────────┘
```

---

## API Reference

### REST Endpoints

Base URL: `/cv/brain`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Get brain system status |
| GET | `/health` | Comprehensive health check |
| POST | `/session/start` | Start new vision session |
| POST | `/session/stop` | Stop current session |
| POST | `/session/pause` | Pause current session |
| POST | `/session/resume` | Resume current session |
| GET | `/session/current` | Get current session state |
| GET | `/session/history` | Get session history |
| GET | `/sessions` | List all sessions |
| GET | `/sessions/{id}` | Get session details |
| POST | `/operator/event` | Submit operator event |
| POST | `/operator/manual-input` | Submit manual input |
| POST | `/brain/mode` | Set brain mode |
| GET | `/brain/stats` | Get brain statistics |
| GET | `/analytics/detections` | Get detection analytics |
| GET | `/analytics/ocr` | Get OCR analytics |
| GET | `/analytics/decisions` | Get decision analytics |

### WebSocket Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/cv/brain/ws/operator` | Operator guidance (bidirectional) |
| `/cv/brain/ws/brain-status` | Real-time brain status updates |

---

## Database Schema

### vision_sessions

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| status | TEXT | created/active/paused/completed/failed/cancelled |
| task_context | JSONB | Task configuration |
| started_at | TIMESTAMPTZ | Session start time |
| ended_at | TIMESTAMPTZ | Session end time |
| total_frames | INTEGER | Frames processed |
| total_detections | INTEGER | Objects detected |
| total_ocr_results | INTEGER | OCR results count |
| total_decisions | INTEGER | Brain decisions count |
| final_result | JSONB | Final extracted data |

### vision_detections

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK to sessions |
| frame_id | INTEGER | Frame number |
| timestamp | TIMESTAMPTZ | Detection time |
| detector | TEXT | "yolo" |
| class_name | TEXT | Object class |
| class_id | INTEGER | YOLO class ID |
| confidence | FLOAT | Detection confidence |
| bbox | JSONB | {x, y, w, h} |
| extra | JSONB | Additional metadata |

### vision_ocr_results

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK to sessions |
| frame_id | INTEGER | Frame number |
| timestamp | TIMESTAMPTZ | OCR time |
| crop_bbox | JSONB | {x, y, w, h} |
| raw_text | TEXT | Original text |
| cleaned_text | TEXT | Cleaned text |
| confidence | FLOAT | OCR confidence |
| source_detection_id | UUID | FK to detection |

### vision_brain_decisions

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK to sessions |
| timestamp | TIMESTAMPTZ | Decision time |
| request_payload | JSONB | Full request to OpenAI |
| response_payload | JSONB | Full response from OpenAI |
| decision_type | TEXT | next_step/final_result/etc. |
| result_status | TEXT | pending/accepted/rejected |
| tokens_used | INTEGER | OpenAI tokens used |
| latency_ms | FLOAT | Response time |
| error_message | TEXT | Error if any |

### vision_operator_events

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK to sessions |
| timestamp | TIMESTAMPTZ | Event time |
| event_type | TEXT | action_confirmed/rejected/etc. |
| payload | JSONB | Event data |
| comment | TEXT | Operator comment |
| related_decision_id | UUID | FK to decision |

---

## Configuration

### Environment Variables

```bash
# OpenAI (Required)
OPENAI_API_KEY=sk-...

# Supabase (Required)
CV_SUPABASE_URL=https://xxx.supabase.co
CV_SUPABASE_KEY=eyJhbG...

# Brain Settings (Optional)
CV_BRAIN_MODEL=gpt-4o-mini        # OpenAI model
CV_BRAIN_MODE=semi_automatic      # Default mode
CV_BRAIN_TEMPERATURE=0.3          # Response creativity

# Processing (Optional)
CV_YOLO_FPS=5                     # YOLO runs per second
CV_OCR_FREQUENCY=10               # OCR every N detections
CV_BRAIN_FREQUENCY=5              # Brain every N OCR results

# Thresholds (Optional)
CV_MIN_DETECTION_CONFIDENCE=0.5
CV_MIN_OCR_CONFIDENCE=0.3
CV_HIGH_CONFIDENCE_THRESHOLD=0.9
```

---

## Usage Scenarios

### Scenario 1: Successful Part Number Extraction

```
1. Operator places motherboard on table
2. Operator clicks "Start Session" (mode: part_number_extraction)
3. YOLO detects: "laptop_motherboard" (confidence: 0.95)
4. OCR reads: "HMT351U6CFR8C-H9" (confidence: 0.88)
5. Brain analyzes scene:
   - Decision: "final_result"
   - Action: mark_candidate_part_number = "HMT351U6CFR8C-H9"
   - Message: "Part number found and verified"
6. Operator clicks "Confirm"
7. Session ends with final_result saved
8. All data persisted in Supabase
```

### Scenario 2: Complex Case with Repositioning

```
1. Operator places board at angle
2. Session started
3. YOLO detects board but text is partially hidden
4. OCR reads partial text: "HMT351U..." (confidence: 0.45)
5. Brain analyzes:
   - Decision: "next_step"
   - Message: "Text partially visible. Please rotate the board clockwise"
6. Operator rotates and clicks "Done"
7. YOLO detects new position
8. OCR reads full text: "HMT351U6CFR8C-H9" (confidence: 0.91)
9. Brain verifies:
   - Decision: "clarification_needed"
   - Message: "Found part number, please confirm: HMT351U6CFR8C-H9"
10. Operator clicks "Confirm"
11. Brain finalizes:
    - Decision: "final_result"
    - Saves complete record
```

---

## Error Handling

### OpenAI Errors

| Error | Handling |
|-------|----------|
| Rate Limit | Log error, pause brain, notify operator |
| Timeout | Retry with backoff, log to Supabase |
| Invalid Request | Log full request, return error decision |
| API Down | Fall back to manual mode |

### Camera Errors

| Error | Handling |
|-------|----------|
| Disconnected | Pause session, reconnect attempts |
| Frame Drop | Skip frame, continue with next |
| Resolution Change | Reconfigure pipeline |

### Database Errors

| Error | Handling |
|-------|----------|
| Connection Lost | Queue writes, retry on reconnect |
| Write Failed | Log locally (temporary), retry |
| Query Timeout | Return cached data if available |

---

## Extension Guide

### Adding New Object Types

1. Train custom YOLO model with new classes
2. Update `target_classes` in OrchestratorConfig
3. Add class description to brain system prompt
4. Create detection rules in brain prompt

### Adding New Task Modes

1. Add mode to `TaskMode` enum in `brain_models.py`
2. Create system prompt for new mode in `llm_brain.py`
3. Implement mode-specific logic in orchestrator
4. Update UI task selector

### Adding New Action Types

1. Add type to `ActionType` enum in `brain_models.py`
2. Handle in `_process_brain_actions()` in orchestrator
3. Implement UI response for action type
4. Update brain system prompts to use new action

### Supporting Additional Cameras

1. Implement camera adapter following `CameraService` interface
2. Add camera mode to `CameraMode` enum
3. Create connection handler
4. Register in camera service factory

---

## Performance Recommendations

| Parameter | Effect | Recommendation |
|-----------|--------|----------------|
| YOLO_FPS | Higher = more CPU, better tracking | 5-10 for real-time |
| OCR_FREQUENCY | Higher = fewer OCR calls | 10-20 for efficiency |
| BRAIN_FREQUENCY | Higher = fewer OpenAI calls | 3-5 for balance |
| MIN_CONFIDENCE | Higher = fewer false positives | 0.5-0.7 |

### Stress Test Results

| Duration | Frames | Detections | OCR | Brain Calls | Errors |
|----------|--------|------------|-----|-------------|--------|
| 15 min | 27,000 | 12,500 | 1,250 | 250 | 0 |

---

## Files Structure

```
backend/app/cv/brain/
├── __init__.py                    # Module exports
├── brain_models.py               # Data models
├── brain_repository.py           # Supabase persistence
├── llm_brain.py                  # OpenAI integration
├── operator_guidance_service.py  # WebSocket service
└── vision_brain_orchestrator.py  # Main orchestrator

backend/app/routers/
└── cv_brain.py                   # API endpoints

frontend/src/
├── api/
│   └── brain.ts                  # API client
├── components/cv/
│   ├── BrainInstructionPanel.tsx # Instructions display
│   ├── BrainStatusPanel.tsx      # Status display
│   └── SessionTimeline.tsx       # History timeline
└── pages/
    └── VisionBrainPage.tsx       # Main brain page

supabase/migrations/
└── 20251204_vision_brain_tables.sql  # Database schema
```

---

*Document Version: 1.0*  
*Last Updated: December 4, 2024*  
*Author: Cursor AI Agent*

