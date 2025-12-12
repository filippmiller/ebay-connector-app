# Computer Vision Module

## Overview

Full-featured computer vision module for DJI Osmo Pocket 3 camera integration with real-time object detection, OCR, and Supabase data persistence.

## Features

- **Camera Support**: DJI Osmo Pocket 3 via UVC (USB Video Class) or RTMP streaming
- **Object Detection**: YOLOv8 real-time detection
- **OCR**: Multi-engine support (EasyOCR, PaddleOCR, Tesseract)
- **Live Streaming**: WebSocket-based MJPEG streaming to web UI
- **Data Persistence**: All results saved to Supabase (no local storage)
- **Debug Console**: Real-time log streaming
- **Health Monitoring**: Component status and metrics

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CV Pipeline                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐ │
│  │  Camera  │──▶│  Vision  │──▶│   OCR    │──▶│   Supabase   │ │
│  │ Service  │   │ Service  │   │ Service  │   │    Writer    │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘ │
│       │              │              │                           │
│       ▼              ▼              ▼                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Stream Router                          │   │
│  │              (WebSocket Broadcasting)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│                    ┌─────────────┐                              │
│                    │  Frontend   │                              │
│                    │ (Web Admin) │                              │
│                    └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Backend Services

| Service | File | Description |
|---------|------|-------------|
| `CameraService` | `camera_service.py` | Camera capture (UVC/RTMP/RTSP) |
| `VisionService` | `vision_service.py` | YOLOv8 object detection |
| `OCRService` | `ocr_service.py` | Text recognition (EasyOCR/PaddleOCR/Tesseract) |
| `SupabaseWriter` | `supabase_writer.py` | Database persistence |
| `StreamRouter` | `stream_router.py` | WebSocket video streaming |
| `CVLogger` | `cv_logger.py` | Structured logging with loguru |
| `CVPipeline` | `cv_pipeline.py` | Main orchestration pipeline |

### Frontend Components

| Component | File | Description |
|-----------|------|-------------|
| `VideoPlayer` | `VideoPlayer.tsx` | Live video stream display |
| `DebugConsole` | `DebugConsole.tsx` | Real-time log viewer |
| `OCRLogsViewer` | `OCRLogsViewer.tsx` | OCR results table |
| `MetricsPanel` | `MetricsPanel.tsx` | System metrics display |
| `CameraVisionPage` | `CameraVisionPage.tsx` | Main admin page |

## Installation

### Backend

```bash
# Install CV dependencies
cd backend
pip install -r app/cv/requirements-cv.txt

# Or with poetry
poetry install --extras cv
```

### System Requirements

- **Tesseract** (if using Tesseract OCR):
  ```bash
  # Ubuntu/Debian
  sudo apt install tesseract-ocr
  
  # Windows
  # Download from: https://github.com/UB-Mannheim/tesseract/wiki
  
  # macOS
  brew install tesseract
  ```

- **CUDA** (optional, for GPU acceleration):
  - Install CUDA Toolkit 11.8+
  - Install cuDNN 8.6+

## Configuration

Environment variables (prefix with `CV_`):

```env
# Camera
CV_CAMERA_MODE=uvc          # uvc, rtmp, rtsp, file
CV_CAMERA_DEVICE_ID=0
CV_CAMERA_RTMP_URL=         # For RTMP mode
CV_CAMERA_WIDTH=1920
CV_CAMERA_HEIGHT=1080
CV_CAMERA_FPS=30

# Vision
CV_YOLO_MODEL=yolov8n.pt    # n/s/m/l/x variants
CV_YOLO_CONFIDENCE=0.5
CV_YOLO_DEVICE=cpu          # cpu or cuda

# OCR
CV_OCR_ENGINE=easyocr       # easyocr, paddleocr, tesseract
CV_OCR_LANGUAGES=en,ru
CV_OCR_GPU=false

# Processing
CV_PROCESS_EVERY_N_FRAMES=5
CV_OCR_EVERY_N_FRAMES=30

# Supabase
CV_SUPABASE_URL=https://xxx.supabase.co
CV_SUPABASE_KEY=your-key

# Logging
CV_LOG_LEVEL=INFO
CV_LOG_TO_SUPABASE=true
```

## Database Schema

### Tables

```sql
-- OCR Results
CREATE TABLE camera_ocr_logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    raw_text TEXT,
    cleaned_text TEXT,
    confidence_score FLOAT,
    source_frame_number INTEGER,
    camera_id TEXT,
    crop_image_url TEXT
);

-- System Logs
CREATE TABLE camera_logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    level TEXT,           -- debug/info/warn/error
    subsystem TEXT,       -- CAMERA/STREAM/CV/OCR/SUPABASE/ERROR
    message TEXT,
    payload JSONB
);

-- Sessions
CREATE TABLE camera_sessions (
    id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    status TEXT,
    total_frames INTEGER,
    total_detections INTEGER,
    total_ocr_results INTEGER
);
```

### Storage Buckets

- `camera_crops`: Cropped text regions
- `camera_debug_frames`: Debug frames with annotations

## API Endpoints

### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cv/health` | Health status |
| GET | `/cv/status` | Pipeline status |
| GET | `/cv/metrics` | Current metrics |
| POST | `/cv/pipeline/start` | Start pipeline |
| POST | `/cv/pipeline/stop` | Stop pipeline |
| POST | `/cv/pipeline/pause` | Pause processing |
| POST | `/cv/pipeline/resume` | Resume processing |
| GET | `/cv/camera/list` | List cameras |
| POST | `/cv/camera/connect` | Connect camera |
| POST | `/cv/camera/disconnect` | Disconnect camera |
| GET | `/cv/ocr/logs` | Get OCR results |
| GET | `/cv/logs` | Get system logs |
| GET | `/cv/config` | Get configuration |
| PUT | `/cv/config` | Update configuration |

### WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/cv/stream` | Live video stream (MJPEG) |
| `/cv/logs/stream` | Real-time log stream |
| `/cv/metrics/stream` | Real-time metrics |

## DJI Osmo Pocket 3 Setup

### UVC Mode (Recommended)

1. Connect camera via USB-C
2. Enable UVC mode on camera:
   - Settings → Connection → USB Connection → Webcam
3. Camera will appear as standard webcam device

### RTMP Mode

1. Configure RTMP server (nginx-rtmp or similar)
2. Set camera to stream to RTMP URL
3. Configure `CV_CAMERA_RTMP_URL` in environment

## Usage

### Starting the Pipeline

```python
from app.cv import CVPipeline

# Create and initialize
pipeline = CVPipeline()
await pipeline.initialize()

# Start processing
await pipeline.start()

# ... processing runs in background ...

# Stop when done
await pipeline.stop()
```

### Via API

```bash
# Start pipeline
curl -X POST http://localhost:8000/cv/pipeline/start

# Check status
curl http://localhost:8000/cv/status

# Stop pipeline
curl -X POST http://localhost:8000/cv/pipeline/stop
```

### Frontend

Navigate to `/admin/camera-vision` in the web admin.

## Performance Considerations

- **CPU Mode**: ~5-10 FPS with YOLOv8n
- **GPU Mode (CUDA)**: ~30+ FPS with YOLOv8n
- **OCR**: EasyOCR is slower but more accurate
- **Streaming**: Reduce quality/FPS for better network performance

## Troubleshooting

### Camera Not Detected

1. Check USB connection
2. Verify UVC mode is enabled on camera
3. Try different device ID (0, 1, 2...)
4. Check camera permissions

### Low FPS

1. Reduce resolution: `CV_CAMERA_WIDTH=1280`
2. Increase frame skip: `CV_PROCESS_EVERY_N_FRAMES=10`
3. Use smaller YOLO model: `CV_YOLO_MODEL=yolov8n.pt`
4. Enable GPU if available

### OCR Quality Issues

1. Ensure good lighting
2. Try different OCR engine
3. Adjust confidence threshold
4. Check language settings

## License

Internal use only. Part of eBay Connector App.

