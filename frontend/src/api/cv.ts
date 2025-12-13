/**
 * Computer Vision API Client
 * 
 * Handles all API calls to the CV module endpoints
 */

import apiClient from '../lib/apiClient';

const API_BASE = '/cv';

// Types
export interface CameraInfo {
  device_id: number;
  name: string;
  width: number;
  height: number;
  fps: number;
}

export interface PipelineStats {
  state: string;
  uptime_seconds: number;
  frames_processed: number;
  detections_total: number;
  ocr_results_total: number;
  avg_fps: number;
  avg_cv_time_ms: number;
  avg_ocr_time_ms: number;
}

export interface CVMetrics {
  fps: number;
  frames_processed: number;
  ocr_count: number;
  errors: number;
  last_error: { message: string; timestamp: string; subsystem: string } | null;
  camera_status: string;
  cv_status: string;
  ocr_status: string;
  supabase_status: string;
}

export interface OCRLog {
  id: string;
  timestamp: string;
  raw_text: string;
  cleaned_text: string;
  confidence_score: number;
  source_frame_number: number;
  camera_id: string;
  crop_image_url?: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  subsystem: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface HealthStatus {
  status: string;
  pipeline: {
    state: string;
    running: boolean;
    stats: PipelineStats;
  };
  camera: Record<string, unknown>;
  vision: Record<string, unknown>;
  ocr: Record<string, unknown>;
  supabase: Record<string, unknown>;
  stream: Record<string, unknown>;
  metrics: CVMetrics;
}

export interface CVConfig {
  camera: {
    mode: string;
    device_id: number;
    width: number;
    height: number;
    fps: number;
  };
  vision: {
    yolo_model: string;
    confidence: number;
    device: string;
  };
  ocr: {
    engine: string;
    languages: string[];
    confidence_threshold: number;
  };
  processing: {
    process_every_n_frames: number;
    ocr_every_n_frames: number;
  };
  stream: {
    quality: number;
    max_fps: number;
  };
}

// API Functions
export const cvApi = {
  // Health & Status
  async getHealth(): Promise<HealthStatus> {
    const response = await apiClient.get(`${API_BASE}/health`);
    return response.data;
  },

  async getStatus(): Promise<{ state: string; stats: PipelineStats; camera_connected: boolean }> {
    const response = await apiClient.get(`${API_BASE}/status`);
    return response.data;
  },

  async getMetrics(): Promise<CVMetrics> {
    const response = await apiClient.get(`${API_BASE}/metrics`);
    return response.data;
  },

  // Pipeline Control
  async startPipeline(): Promise<{ status: string; message: string }> {
    const response = await apiClient.post(`${API_BASE}/pipeline/start`);
    return response.data;
  },

  async stopPipeline(): Promise<{ status: string; message: string }> {
    const response = await apiClient.post(`${API_BASE}/pipeline/stop`);
    return response.data;
  },

  async pausePipeline(): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/pipeline/pause`);
    return response.data;
  },

  async resumePipeline(): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/pipeline/resume`);
    return response.data;
  },

  // Camera
  async listCameras(): Promise<{ cameras: CameraInfo[] }> {
    const response = await apiClient.get(`${API_BASE}/camera/list`);
    return response.data;
  },

  async getCameraStatus(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/camera/status`);
    return response.data;
  },

  async connectCamera(config?: {
    mode?: string;
    device_id?: number;
    rtmp_url?: string;
    width?: number;
    height?: number;
    fps?: number;
  }): Promise<{ status: string; info: CameraInfo }> {
    const response = await apiClient.post(`${API_BASE}/camera/connect`, config);
    return response.data;
  },

  async disconnectCamera(): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/camera/disconnect`);
    return response.data;
  },

  // Vision
  async getVisionStatus(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/vision/status`);
    return response.data;
  },

  async getVisionStats(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/vision/stats`);
    return response.data;
  },

  // OCR
  async getOCRStatus(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/ocr/status`);
    return response.data;
  },

  async getOCRStats(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/ocr/stats`);
    return response.data;
  },

  async getOCRLogs(params?: {
    limit?: number;
    offset?: number;
    camera_id?: string;
    min_confidence?: number;
  }): Promise<{ logs: OCRLog[]; count: number; offset: number; limit: number }> {
    const response = await apiClient.get(`${API_BASE}/ocr/logs`, { params });
    return response.data;
  },

  // Logs
  async getRecentLogs(count?: number): Promise<{ logs: LogEntry[] }> {
    const response = await apiClient.get(`${API_BASE}/logs/recent`, {
      params: { count },
    });
    return response.data;
  },

  async getLogs(params?: {
    limit?: number;
    offset?: number;
    level?: string;
    subsystem?: string;
  }): Promise<{ logs: LogEntry[]; count: number }> {
    const response = await apiClient.get(`${API_BASE}/logs`, { params });
    return response.data;
  },

  // Config
  async getConfig(): Promise<CVConfig> {
    const response = await apiClient.get(`${API_BASE}/config`);
    return response.data;
  },

  async updateConfig(config: Partial<{
    yolo_model: string;
    confidence: number;
    process_every_n_frames: number;
    ocr_every_n_frames: number;
    ocr_engine: string;
    ocr_languages: string[];
  }>): Promise<{ status: string; config: Record<string, unknown> }> {
    const response = await apiClient.put(`${API_BASE}/config`, config);
    return response.data;
  },
};

// WebSocket helper
export function getStreamWebSocketUrl(mode: 'raw' | 'annotated' = 'raw'): string {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const wsUrl = baseUrl.replace(/^http/, 'ws');
  return `${wsUrl}${API_BASE}/stream?mode=${mode}`;
}

export function getLogsWebSocketUrl(): string {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const wsUrl = baseUrl.replace(/^http/, 'ws');
  return `${wsUrl}${API_BASE}/logs/stream`;
}

export function getMetricsWebSocketUrl(): string {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const wsUrl = baseUrl.replace(/^http/, 'ws');
  return `${wsUrl}${API_BASE}/metrics/stream`;
}

