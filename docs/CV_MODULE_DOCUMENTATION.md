# Computer Vision Module - Full Documentation

## Overview

The Computer Vision (CV) Module is a comprehensive real-time video processing system designed for integration with DJI Osmo Pocket 3 camera. It provides object detection, text recognition (OCR), and live streaming capabilities with full Supabase integration.

**Key Principle:** Zero local storage - all data persists exclusively in Supabase.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Technology Stack](#technology-stack)
3. [Data Flow](#data-flow)
4. [Backend Components](#backend-components)
5. [Frontend Components](#frontend-components)
6. [API Reference](#api-reference)
7. [Database Schema](#database-schema)
8. [Configuration](#configuration)
9. [File Structure](#file-structure)
10. [Deployment](#deployment)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           COMPUTER VISION MODULE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐                                                             │
│  │ DJI Osmo    │                                                             │
│  │ Pocket 3    │                                                             │
│  │ (Camera)    │                                                             │
│  └──────┬──────┘                                                             │
│         │ USB/RTMP/RTSP                                                      │
│         ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        CV PIPELINE                                   │    │
│  │  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌──────────────┐  │    │
│  │  │  Camera   │──▶│  Vision   │──▶│    OCR    │──▶│   Supabase   │  │    │
│  │  │  Service  │   │  Service  │   │  Service  │   │    Writer    │  │    │
│  │  │           │   │  (YOLO)   │   │ (EasyOCR) │   │              │  │    │
│  │  └─────┬─────┘   └─────┬─────┘   └─────┬─────┘   └──────────────┘  │    │
│  │        │               │               │                           │    │
│  │        └───────────────┴───────────────┘                           │    │
│  │                        │                                           │    │
│  │                        ▼                                           │    │
│  │              ┌─────────────────┐                                   │    │
│  │              │  Stream Router  │                                   │    │
│  │              │   (WebSocket)   │                                   │    │
│  │              └────────┬────────┘                                   │    │
│  └───────────────────────┼─────────────────────────────────────────────┘    │
│                          │                                                   │
│         ┌────────────────┼────────────────┐                                 │
│         │                │                │                                 │
│         ▼                ▼                ▼                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │   Video     │  │    Logs     │  │   Metrics   │                         │
│  │   Stream    │  │   Stream    │  │   Stream    │                         │
│  │ /cv/stream  │  │/cv/logs/    │  │/cv/metrics/ │                         │
│  │             │  │   stream    │  │   stream    │                         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
│         │                │                │                                 │
│         └────────────────┴────────────────┘                                 │
│                          │                                                   │
│                          ▼                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         FRONTEND (React)                             │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │    │
│  │  │   Video     │  │   Debug     │  │  OCR Logs   │  │  Metrics   │  │    │
│  │  │   Player    │  │   Console   │  │   Viewer    │  │   Panel    │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────┬──────────────────────────┘
                                                   │
                                                   ▼
                                          ┌───────────────┐
                                          │   SUPABASE    │
                                          │  ┌─────────┐  │
                                          │  │ Tables  │  │
                                          │  │ Storage │  │
                                          │  └─────────┘  │
                                          └───────────────┘
```

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12+ | Runtime |
| FastAPI | 0.119+ | Web framework |
| OpenCV | 4.10.x | Video capture & processing |
| Ultralytics | 8.3.x | YOLOv8 object detection |
| EasyOCR | 1.7.x | Text recognition |
| PaddleOCR | 2.7.x | Alternative OCR engine |
| Tesseract | 5.x | Alternative OCR engine |
| Loguru | 0.7.x | Structured logging |
| Supabase-py | 2.10.x | Database client |
| NumPy | 1.26.x | Array operations |
| Pillow | 10.x | Image processing |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3.x | UI framework |
| TypeScript | 5.6.x | Type safety |
| Vite | 6.x | Build tool |
| TailwindCSS | 3.4.x | Styling |
| Radix UI | Latest | UI components |
| Lucide React | 0.364.x | Icons |
| Sonner | 2.x | Toast notifications |

### Infrastructure

| Service | Purpose |
|---------|---------|
| Railway | Backend hosting |
| Supabase | Database + Storage |
| Cloudflare Pages | Frontend hosting |

---

## Data Flow

### Frame Processing Pipeline

```
1. CAPTURE
   Camera (DJI Osmo Pocket 3)
   └── UVC Mode (USB Video Class) / RTMP / RTSP
       └── OpenCV VideoCapture
           └── Frame object created
               ├── frame_number
               ├── timestamp
               ├── width/height
               └── raw data (numpy array)

2. DETECTION (every N frames)
   Vision Service
   └── YOLOv8 Model
       └── Detections[]
           ├── class_id
           ├── class_name
           ├── confidence
           ├── bounding box (x1,y1,x2,y2)
           └── center point

3. TEXT DETECTION
   Vision Service
   └── Adaptive Thresholding
       └── Contour Detection
           └── TextRegion[]
               ├── bounding box
               └── cropped image

4. OCR (every M frames)
   OCR Service
   └── EasyOCR / PaddleOCR / Tesseract
       └── OCRResult[]
           ├── raw_text
           ├── cleaned_text
           ├── confidence
           └── bounding box

5. PERSISTENCE
   Supabase Writer
   └── Batch Insert Queue
       ├── camera_ocr_logs (OCR results)
       ├── camera_logs (system logs)
       └── camera_frames (optional key frames)

6. STREAMING
   Stream Router
   └── WebSocket Broadcast
       ├── /cv/stream (video frames - MJPEG)
       ├── /cv/logs/stream (log entries)
       └── /cv/metrics/stream (performance data)
```

### Log Flow

```
Any Service → CVLogger
                │
                ├── Console (loguru formatted)
                │
                ├── File (errors only)
                │
                ├── Memory Buffer (recent logs)
                │
                ├── WebSocket Broadcast (live)
                │
                └── Supabase (persistent)
```

---

## Backend Components

### 1. Configuration (`config.py`)

**Purpose:** Centralized settings management using Pydantic

```python
class CVSettings(BaseSettings):
    # Camera
    camera_mode: CameraMode      # uvc, rtmp, rtsp, file
    camera_device_id: int        # UVC device index
    camera_width: int            # Frame width
    camera_height: int           # Frame height
    camera_fps: int              # Target FPS
    
    # Vision
    yolo_model: str              # yolov8n.pt, yolov8s.pt, etc.
    yolo_confidence: float       # Detection threshold
    yolo_device: str             # cpu or cuda
    
    # OCR
    ocr_engine: OCREngine        # easyocr, paddleocr, tesseract
    ocr_languages: List[str]     # ['en', 'ru']
    ocr_confidence_threshold: float
    
    # Processing
    process_every_n_frames: int  # CV frequency
    ocr_every_n_frames: int      # OCR frequency
    
    # Supabase
    supabase_url: str
    supabase_key: str
```

**Enums:**
- `CameraMode`: UVC, RTMP, RTSP, FILE
- `OCREngine`: EASYOCR, PADDLEOCR, TESSERACT

---

### 2. Logger (`cv_logger.py`)

**Purpose:** Structured logging with subsystem tagging

**Class:** `CVLogger` (Singleton)

**Subsystems:**
| Tag | Description |
|-----|-------------|
| `[CAMERA]` | Camera connection & capture |
| `[STREAM]` | Video streaming |
| `[CV]` | Object detection |
| `[OCR]` | Text recognition |
| `[SUPABASE]` | Database operations |
| `[ERROR]` | Error events |
| `[SYSTEM]` | Pipeline lifecycle |

**Methods:**
```python
cv_logger.camera("message", level=LogLevel.INFO, payload={})
cv_logger.stream("message", ...)
cv_logger.cv("message", ...)
cv_logger.ocr("message", ...)
cv_logger.supabase("message", ...)
cv_logger.error("message", subsystem="CV", ...)
cv_logger.system("message", ...)

# Metrics
cv_logger.update_fps(fps: float)
cv_logger.increment_frames()
cv_logger.increment_ocr()
cv_logger.set_status(component: str, status: str)
cv_logger.get_metrics() -> Dict
cv_logger.get_recent_logs(count: int) -> List[Dict]
```

---

### 3. Camera Service (`camera_service.py`)

**Purpose:** Video capture from DJI Osmo Pocket 3

**Class:** `CameraService`

**States:**
```
DISCONNECTED → CONNECTING → CONNECTED → STREAMING
                    ↓                       ↓
                 ERROR ←──────────── RECONNECTING
```

**Key Methods:**
```python
# Connection
list_cameras() -> List[CameraInfo]
connect() -> bool
disconnect()

# Streaming
start_streaming() -> bool
stop_streaming()

# Frame Access
get_frame(timeout: float) -> Optional[Frame]
get_latest_frame() -> Optional[Frame]
frame_generator() -> Generator[Frame]

# Callbacks
register_frame_callback(callback: Callable[[Frame], None])
unregister_frame_callback(callback)

# Health
health_check() -> Dict
```

**Frame Object:**
```python
@dataclass
class Frame:
    data: np.ndarray        # BGR image
    frame_number: int
    timestamp: float
    width: int
    height: int
```

**DJI Osmo Pocket 3 Connection Modes:**

| Mode | Setup | Use Case |
|------|-------|----------|
| UVC | USB-C → Camera Settings → Webcam | Direct, highest quality |
| RTMP | Camera → Live Stream → Custom RTMP | Remote streaming |
| RTSP | Via capture card/converter | Professional setups |

---

### 4. Vision Service (`vision_service.py`)

**Purpose:** Object detection using YOLOv8

**Class:** `VisionService`

**Key Methods:**
```python
load_model() -> bool
detect_objects(frame: Frame) -> List[Detection]
detect_text_regions(frame: Frame) -> List[TextRegion]
process_frame(frame: Frame) -> VisionResult
draw_detections(frame: np.ndarray, result: VisionResult) -> np.ndarray
zoom_to_region(frame: np.ndarray, bbox: Tuple, zoom: float) -> np.ndarray
```

**Detection Object:**
```python
@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    center: Tuple[int, int]
    area: int
```

**VisionResult Object:**
```python
@dataclass
class VisionResult:
    frame_number: int
    timestamp: float
    detections: List[Detection]
    text_regions: List[TextRegion]
    processing_time_ms: float
```

**YOLO Models:**
| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| yolov8n.pt | 6MB | Fastest | Good |
| yolov8s.pt | 22MB | Fast | Better |
| yolov8m.pt | 52MB | Medium | High |
| yolov8l.pt | 87MB | Slow | Higher |
| yolov8x.pt | 137MB | Slowest | Highest |

---

### 5. OCR Service (`ocr_service.py`)

**Purpose:** Text recognition with multiple engine support

**Class:** `OCRService`

**Engines:**

| Engine | Pros | Cons |
|--------|------|------|
| EasyOCR | Multi-language, GPU support, accurate | Slower |
| PaddleOCR | Fast, lightweight, 80+ languages | Setup complexity |
| Tesseract | Classic, fast, well-documented | Lower accuracy |

**Key Methods:**
```python
initialize(engine: OCREngine) -> bool
recognize_image(image: np.ndarray) -> List[OCRResult]
process_text_regions(regions, frame_number, timestamp) -> OCRBatchResult
identify_pattern(text: str) -> Optional[str]  # SKU, barcode, serial, etc.
extract_codes(results: List[OCRResult]) -> List[Dict]
```

**OCRResult Object:**
```python
@dataclass
class OCRResult:
    raw_text: str
    cleaned_text: str
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]]
    language: Optional[str]
```

**Pattern Recognition:**
| Pattern | Regex | Example |
|---------|-------|---------|
| SKU | `^[A-Z0-9]{4,20}$` | ABC123XYZ |
| Barcode | `^\d{8,14}$` | 012345678901 |
| Serial | `^[A-Z0-9\-]{6,30}$` | SN-12345-ABC |
| Part Number | `^[A-Z]{1,3}[\-\s]?\d{3,10}$` | PT-123456 |

---

### 6. Supabase Writer (`supabase_writer.py`)

**Purpose:** Async batch persistence to Supabase

**Class:** `SupabaseWriter`

**Features:**
- Background write queue
- Batch inserts (configurable size)
- Auto-flush interval
- Retry on failure
- Image upload to Storage

**Key Methods:**
```python
initialize() -> bool
write_ocr_result(entry: OCRLogEntry) -> bool
write_log(log_entry: Dict) -> bool
upload_image(image: np.ndarray, bucket: str, filename: str) -> Optional[str]
upload_crop(image, frame_number, region_index) -> Optional[str]
upload_debug_frame(image, frame_number) -> Optional[str]
shutdown()
```

**OCRLogEntry Object:**
```python
@dataclass
class OCRLogEntry:
    raw_text: str
    cleaned_text: str
    confidence_score: float
    source_frame_number: int
    camera_id: str = "default"
    crop_image_url: Optional[str] = None
    timestamp: Optional[str] = None  # Auto-generated
```

---

### 7. Stream Router (`stream_router.py`)

**Purpose:** WebSocket video/log broadcasting

**Classes:**
- `StreamRouter` - Video stream management
- `LogStreamRouter` - Log stream management

**Stream Modes:**
| Mode | Description |
|------|-------------|
| `raw` | Original video frames |
| `annotated` | Frames with CV overlays |
| `both` | Side-by-side view |

**StreamRouter Methods:**
```python
connect(websocket, client_id, mode) -> bool
disconnect(client_id)
broadcast_frame(frame: Frame, vision_result: Optional[VisionResult])
broadcast_message(message: Dict)
handle_client_message(client_id, message)
start_broadcast_loop()
stop_broadcast_loop()
```

**WebSocket Message Format (Video):**
```json
{
  "type": "frame",
  "frame_number": 12345,
  "timestamp": 1701234567.123,
  "width": 1920,
  "height": 1080,
  "data": "<base64 JPEG>",
  "detections": 5,
  "text_regions": 2
}
```

**WebSocket Message Format (Logs):**
```json
{
  "timestamp": "2024-12-04T12:00:00.000Z",
  "level": "info",
  "subsystem": "CV",
  "message": "Detected 5 objects",
  "payload": {}
}
```

---

### 8. CV Pipeline (`cv_pipeline.py`)

**Purpose:** Main orchestration of all services

**Class:** `CVPipeline`

**States:**
```
STOPPED → STARTING → RUNNING ⇄ PAUSED
              ↓
           ERROR
```

**Lifecycle:**
```python
pipeline = CVPipeline()
await pipeline.initialize()    # Load all services
await pipeline.start()         # Begin processing
# ... running ...
await pipeline.pause()         # Pause processing
await pipeline.resume()        # Resume processing
await pipeline.stop()          # Cleanup
```

**Key Methods:**
```python
initialize() -> bool
start() -> bool
stop()
pause()
resume()
get_stats() -> PipelineStats
health_check() -> Dict

# Service accessors
@property camera: CameraService
@property vision: VisionService
@property ocr: OCRService
@property supabase: SupabaseWriter
@property stream_router: StreamRouter
@property log_router: LogStreamRouter
```

**PipelineStats:**
```python
@dataclass
class PipelineStats:
    state: str
    uptime_seconds: float
    frames_processed: int
    detections_total: int
    ocr_results_total: int
    avg_fps: float
    avg_cv_time_ms: float
    avg_ocr_time_ms: float
```

---

### 9. API Router (`routers/cv_camera.py`)

**Purpose:** REST API and WebSocket endpoints

**Prefix:** `/cv`

**REST Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Full health status |
| GET | `/status` | Pipeline status |
| GET | `/metrics` | Current metrics |
| POST | `/pipeline/start` | Start pipeline |
| POST | `/pipeline/stop` | Stop pipeline |
| POST | `/pipeline/pause` | Pause processing |
| POST | `/pipeline/resume` | Resume processing |
| GET | `/camera/list` | List available cameras |
| GET | `/camera/status` | Camera status |
| POST | `/camera/connect` | Connect to camera |
| POST | `/camera/disconnect` | Disconnect camera |
| GET | `/vision/status` | Vision service status |
| GET | `/vision/stats` | Vision statistics |
| GET | `/ocr/status` | OCR service status |
| GET | `/ocr/stats` | OCR statistics |
| GET | `/ocr/logs` | Get OCR results |
| GET | `/logs/recent` | Recent logs from memory |
| GET | `/logs` | Logs from Supabase |
| GET | `/config` | Current configuration |
| PUT | `/config` | Update configuration |

**WebSocket Endpoints:**

| Endpoint | Protocol | Description |
|----------|----------|-------------|
| `/cv/stream` | WS | Live video stream |
| `/cv/logs/stream` | WS | Real-time logs |
| `/cv/metrics/stream` | WS | Real-time metrics |

---

## Frontend Components

### 1. API Client (`api/cv.ts`)

**Purpose:** TypeScript API wrapper

**Functions:**
```typescript
cvApi.getHealth(): Promise<HealthStatus>
cvApi.getStatus(): Promise<StatusResponse>
cvApi.getMetrics(): Promise<CVMetrics>
cvApi.startPipeline(): Promise<Response>
cvApi.stopPipeline(): Promise<Response>
cvApi.pausePipeline(): Promise<Response>
cvApi.resumePipeline(): Promise<Response>
cvApi.listCameras(): Promise<CamerasResponse>
cvApi.connectCamera(config): Promise<Response>
cvApi.disconnectCamera(): Promise<Response>
cvApi.getOCRLogs(params): Promise<OCRLogsResponse>
cvApi.getRecentLogs(count): Promise<LogsResponse>
cvApi.getConfig(): Promise<CVConfig>
cvApi.updateConfig(config): Promise<Response>

// WebSocket URL helpers
getStreamWebSocketUrl(mode): string
getLogsWebSocketUrl(): string
getMetricsWebSocketUrl(): string
```

---

### 2. VideoPlayer (`components/cv/VideoPlayer.tsx`)

**Purpose:** Live video display with WebSocket

**Features:**
- WebSocket MJPEG streaming
- Mode toggle (raw/annotated)
- FPS display
- Detection counters
- Fullscreen support
- Auto-reconnection

**Props:**
```typescript
interface VideoPlayerProps {
  autoConnect?: boolean;    // Auto-connect on mount
  showControls?: boolean;   // Show control bar
  className?: string;
}
```

---

### 3. DebugConsole (`components/cv/DebugConsole.tsx`)

**Purpose:** Real-time log viewer

**Features:**
- WebSocket log streaming
- Subsystem filtering
- Level filtering
- Text search
- Pause/resume
- Download logs
- Clear logs
- Color-coded by subsystem/level

**Props:**
```typescript
interface DebugConsoleProps {
  autoConnect?: boolean;
  maxLogs?: number;         // Buffer size
  className?: string;
}
```

---

### 4. OCRLogsViewer (`components/cv/OCRLogsViewer.tsx`)

**Purpose:** OCR results table

**Features:**
- Paginated results
- Confidence filter
- Text search
- Copy to clipboard
- Detail dialog
- Crop image preview
- Auto-refresh

**Props:**
```typescript
interface OCRLogsViewerProps {
  className?: string;
  limit?: number;
}
```

---

### 5. MetricsPanel (`components/cv/MetricsPanel.tsx`)

**Purpose:** System metrics display

**Features:**
- Component status indicators
- FPS gauge
- Processing counters
- Error tracking
- Uptime display
- Processing time stats

**Props:**
```typescript
interface MetricsPanelProps {
  className?: string;
  pollInterval?: number;    // ms
}
```

---

### 6. CameraVisionPage (`pages/CameraVisionPage.tsx`)

**Purpose:** Main admin page

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ HEADER: Title, Pipeline State, Start/Stop/Pause Controls        │
├────────────────────────────────────┬────────────────────────────┤
│                                    │                            │
│  Camera Selection & VideoPlayer    │    MetricsPanel            │
│  (8 columns)                       │    (4 columns)             │
│                                    │                            │
├────────────────────────────────────┤    Configuration Card      │
│                                    │                            │
│  Tabs:                             │    Quick Guide Card        │
│  - Debug Console                   │                            │
│  - OCR Results                     │                            │
│                                    │                            │
└────────────────────────────────────┴────────────────────────────┘
```

**URL:** `/admin/camera-vision`

---

## Database Schema

### Tables

#### `camera_ocr_logs`
```sql
CREATE TABLE camera_ocr_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    raw_text TEXT NOT NULL,
    cleaned_text TEXT,
    crop_image_url TEXT,
    source_frame_number INTEGER,
    camera_id TEXT DEFAULT 'default',
    confidence_score FLOAT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_camera_ocr_logs_timestamp ON camera_ocr_logs(timestamp DESC);
CREATE INDEX idx_camera_ocr_logs_camera_id ON camera_ocr_logs(camera_id);
CREATE INDEX idx_camera_ocr_logs_confidence ON camera_ocr_logs(confidence_score);
CREATE INDEX idx_camera_ocr_logs_text_search ON camera_ocr_logs 
    USING gin(to_tsvector('english', raw_text));
```

#### `camera_logs`
```sql
CREATE TABLE camera_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    level TEXT NOT NULL DEFAULT 'info' 
        CHECK (level IN ('debug', 'info', 'warn', 'error', 'critical')),
    subsystem TEXT NOT NULL 
        CHECK (subsystem IN ('CAMERA', 'STREAM', 'CV', 'OCR', 'SUPABASE', 'ERROR', 'SYSTEM')),
    message TEXT NOT NULL,
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_camera_logs_timestamp ON camera_logs(timestamp DESC);
CREATE INDEX idx_camera_logs_level ON camera_logs(level);
CREATE INDEX idx_camera_logs_subsystem ON camera_logs(subsystem);
```

#### `camera_frames`
```sql
CREATE TABLE camera_frames (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    frame_number INTEGER NOT NULL,
    camera_id TEXT DEFAULT 'default',
    image_url TEXT,
    width INTEGER,
    height INTEGER,
    detections JSONB DEFAULT '[]',
    ocr_results JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    processing_time_ms FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### `camera_sessions`
```sql
CREATE TABLE camera_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id TEXT NOT NULL DEFAULT 'default',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    status TEXT DEFAULT 'active' 
        CHECK (status IN ('active', 'ended', 'error')),
    total_frames INTEGER DEFAULT 0,
    total_detections INTEGER DEFAULT 0,
    total_ocr_results INTEGER DEFAULT 0,
    avg_fps FLOAT,
    error_message TEXT,
    config JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}'
);
```

#### `cv_detection_classes`
```sql
CREATE TABLE cv_detection_classes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    class_id INTEGER NOT NULL UNIQUE,
    class_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    min_confidence FLOAT DEFAULT 0.5,
    color TEXT DEFAULT '#00FF00',
    alert_on_detection BOOLEAN DEFAULT false
);
```

### Storage Buckets

| Bucket | Public | Purpose |
|--------|--------|---------|
| `camera_crops` | Yes | Cropped text regions |
| `camera_debug_frames` | No | Debug frames with annotations |

---

## Configuration

### Environment Variables

```bash
# Required
CV_SUPABASE_URL=https://xxx.supabase.co
CV_SUPABASE_KEY=eyJhbG...                    # service_role key

# Camera (optional, has defaults)
CV_CAMERA_MODE=uvc                           # uvc, rtmp, rtsp, file
CV_CAMERA_DEVICE_ID=0
CV_CAMERA_RTMP_URL=                          # For RTMP mode
CV_CAMERA_WIDTH=1920
CV_CAMERA_HEIGHT=1080
CV_CAMERA_FPS=30

# Vision (optional)
CV_YOLO_MODEL=yolov8n.pt
CV_YOLO_CONFIDENCE=0.5
CV_YOLO_DEVICE=cpu                           # cpu or cuda

# OCR (optional)
CV_OCR_ENGINE=easyocr                        # easyocr, paddleocr, tesseract
CV_OCR_LANGUAGES=en,ru
CV_OCR_CONFIDENCE_THRESHOLD=0.3
CV_OCR_GPU=false

# Processing (optional)
CV_PROCESS_EVERY_N_FRAMES=5
CV_OCR_EVERY_N_FRAMES=30

# Stream (optional)
CV_STREAM_QUALITY=80
CV_STREAM_MAX_FPS=30

# Logging (optional)
CV_LOG_LEVEL=INFO
CV_LOG_TO_SUPABASE=true
```

---

## File Structure

```
backend/
├── app/
│   ├── cv/
│   │   ├── __init__.py              # Module exports
│   │   ├── config.py                # Settings & enums
│   │   ├── cv_logger.py             # Logging system
│   │   ├── camera_service.py        # Camera capture
│   │   ├── vision_service.py        # YOLOv8 detection
│   │   ├── ocr_service.py           # OCR engines
│   │   ├── supabase_writer.py       # Database persistence
│   │   ├── stream_router.py         # WebSocket streaming
│   │   ├── cv_pipeline.py           # Main orchestration
│   │   ├── requirements-cv.txt      # CV dependencies
│   │   └── README.md                # Module readme
│   │
│   ├── routers/
│   │   └── cv_camera.py             # API endpoints
│   │
│   └── main.py                      # Router registration

frontend/
├── src/
│   ├── api/
│   │   └── cv.ts                    # API client
│   │
│   ├── components/
│   │   └── cv/
│   │       ├── VideoPlayer.tsx      # Video stream
│   │       ├── DebugConsole.tsx     # Log viewer
│   │       ├── OCRLogsViewer.tsx    # OCR results
│   │       └── MetricsPanel.tsx     # Metrics display
│   │
│   ├── pages/
│   │   └── CameraVisionPage.tsx     # Main page
│   │
│   └── App.tsx                      # Route registration

supabase/
└── migrations/
    └── 20251204_cv_module_tables.sql # Database schema

docs/
└── CV_MODULE_DOCUMENTATION.md       # This file
```

---

## Deployment

### Railway Variables

```
CV_SUPABASE_URL=https://nrpfahjygulsfxmbmfzv.supabase.co
CV_SUPABASE_KEY=<service_role_key>
CV_CAMERA_MODE=uvc
CV_OCR_ENGINE=easyocr
CV_OCR_LANGUAGES=en,ru
CV_LOG_LEVEL=INFO
CV_LOG_TO_SUPABASE=true
```

### Supabase Setup

1. Tables created via migration
2. Storage buckets:
   - `camera_crops` (public)
   - `camera_debug_frames` (private)

### DJI Osmo Pocket 3 Setup

1. Connect camera via USB-C
2. Camera Settings → Connection → USB → Webcam
3. Camera appears as UVC device (index usually 0)

---

## Usage

### Quick Start

1. Navigate to `/admin/camera-vision`
2. Click "Refresh" to detect cameras
3. Select camera from dropdown
4. Click "Connect"
5. Click "Start Pipeline"
6. View live video with CV overlays
7. Check Debug Console for logs
8. View OCR Results tab for recognized text

### API Usage

```bash
# Start pipeline
curl -X POST http://localhost:8000/cv/pipeline/start

# Check status
curl http://localhost:8000/cv/status

# Get OCR results
curl http://localhost:8000/cv/ocr/logs?limit=50

# Stop pipeline
curl -X POST http://localhost:8000/cv/pipeline/stop
```

### WebSocket Client

```javascript
// Video stream
const ws = new WebSocket('ws://localhost:8000/cv/stream?mode=annotated');
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'frame') {
    // data.data contains base64 JPEG
  }
};

// Log stream
const logWs = new WebSocket('ws://localhost:8000/cv/logs/stream');
logWs.onmessage = (e) => {
  const log = JSON.parse(e.data);
  console.log(`[${log.subsystem}] ${log.message}`);
};
```

---

## Performance Tuning

| Parameter | Lower Value | Higher Value |
|-----------|-------------|--------------|
| `PROCESS_EVERY_N_FRAMES` | More accurate | Higher FPS |
| `OCR_EVERY_N_FRAMES` | More OCR results | Lower CPU |
| `YOLO_CONFIDENCE` | More detections | Higher precision |
| `STREAM_QUALITY` | Lower bandwidth | Better image |
| `STREAM_MAX_FPS` | Lower bandwidth | Smoother video |

### GPU Acceleration

```bash
# Enable CUDA
CV_YOLO_DEVICE=cuda
CV_OCR_GPU=true

# Install CUDA dependencies
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

---

*Document Version: 1.0*
*Last Updated: December 4, 2024*

