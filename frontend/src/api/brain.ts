/**
 * Vision Brain API Client
 * 
 * API client for the AI-powered vision brain system
 */

import apiClient from '../lib/apiClient';

const API_BASE = '/cv/brain';

// Types
export interface BrainStatus {
  brain_initialized: boolean;
  brain_mode: string;
  orchestrator_state: string;
  session_active: boolean;
  connected_operators: number;
  stats: {
    total_frames: number;
    total_detections: number;
    total_ocr_results: number;
    total_brain_calls: number;
    total_operator_events: number;
  };
}

export interface VisionSession {
  id: string;
  status: string;
  task_context?: {
    mode: string;
    expected_object_type?: string;
    notes?: string;
  };
  started_at: string;
  ended_at?: string;
  total_frames: number;
  total_detections: number;
  total_ocr_results: number;
  total_decisions: number;
  final_result?: Record<string, unknown>;
}

export interface HistoryEntry {
  role: string;
  type: string;
  message: string;
  timestamp: string;
}

export interface BrainDecision {
  decision_id: string;
  decision_type: string;
  actions: {
    type: string;
    message: string;
    value?: string;
    confidence?: number;
  }[];
  comments: string;
  confidence: number;
}

export interface BrainInstruction {
  type: 'brain_instruction';
  session_id: string;
  decision_id: string;
  decision_type: string;
  messages: string[];
  extracted_values: {
    type: string;
    value: string;
    confidence: number;
  }[];
  confidence: number;
  comments: string;
  actions: {
    type: string;
    id: string;
    label: string;
  }[];
}

export interface SessionState {
  session_id: string | null;
  session_state: string;
  running: boolean;
  task_mode: string | null;
  frame_counter: number;
  detection_counter: number;
  ocr_counter: number;
  history_length: number;
  latest_decision: BrainDecision | null;
  stats: Record<string, number>;
}

// API Functions
export const brainApi = {
  // Status
  async getStatus(): Promise<BrainStatus> {
    const response = await apiClient.get(`${API_BASE}/status`);
    return response.data;
  },

  async getHealth(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/health`);
    return response.data;
  },

  // Session Management
  async startSession(config: {
    mode?: string;
    expected_object_type?: string;
    notes?: string;
    brain_mode?: string;
  }): Promise<{ session_id: string; status: string }> {
    const response = await apiClient.post(`${API_BASE}/session/start`, config);
    return response.data;
  },

  async stopSession(): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/session/stop`);
    return response.data;
  },

  async pauseSession(): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/session/pause`);
    return response.data;
  },

  async resumeSession(): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/session/resume`);
    return response.data;
  },

  async getCurrentSession(): Promise<SessionState> {
    const response = await apiClient.get(`${API_BASE}/session/current`);
    return response.data;
  },

  async getSessionHistory(): Promise<{ history: HistoryEntry[] }> {
    const response = await apiClient.get(`${API_BASE}/session/history`);
    return response.data;
  },

  async listSessions(params?: {
    limit?: number;
    offset?: number;
    status?: string;
  }): Promise<{ sessions: VisionSession[]; count: number }> {
    const response = await apiClient.get(`${API_BASE}/sessions`, { params });
    return response.data;
  },

  async getSessionDetails(sessionId: string): Promise<{
    session: VisionSession;
    detections: unknown[];
    ocr_results: unknown[];
    decisions: unknown[];
    operator_events: unknown[];
  }> {
    const response = await apiClient.get(`${API_BASE}/sessions/${sessionId}`);
    return response.data;
  },

  // Operator Events
  async submitOperatorEvent(event: {
    event_type: string;
    comment?: string;
    payload?: Record<string, unknown>;
  }): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/operator/event`, event);
    return response.data;
  },

  async submitManualInput(field: string, value: string): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/operator/manual-input`, {
      field,
      value,
    });
    return response.data;
  },

  // Brain Control
  async setBrainMode(mode: string): Promise<{ status: string }> {
    const response = await apiClient.post(`${API_BASE}/brain/mode?mode=${mode}`);
    return response.data;
  },

  async getBrainStats(): Promise<Record<string, unknown>> {
    const response = await apiClient.get(`${API_BASE}/brain/stats`);
    return response.data;
  },

  // Analytics
  async getDetectionAnalytics(sessionId?: string): Promise<{
    classes: Record<string, { count: number; avg_confidence: number }>;
    total: number;
  }> {
    const response = await apiClient.get(`${API_BASE}/analytics/detections`, {
      params: { session_id: sessionId },
    });
    return response.data;
  },

  async getOCRAnalytics(sessionId?: string): Promise<{
    texts: Record<string, { count: number; max_confidence: number }>;
    total: number;
  }> {
    const response = await apiClient.get(`${API_BASE}/analytics/ocr`, {
      params: { session_id: sessionId },
    });
    return response.data;
  },

  async getDecisionAnalytics(sessionId?: string): Promise<{
    total: number;
    by_type: Record<string, number>;
    by_status: Record<string, number>;
    avg_latency_ms: number;
    total_tokens: number;
  }> {
    const response = await apiClient.get(`${API_BASE}/analytics/decisions`, {
      params: { session_id: sessionId },
    });
    return response.data;
  },
};

// WebSocket helpers
export function getOperatorWebSocketUrl(): string {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const wsUrl = baseUrl.replace(/^http/, 'ws');
  return `${wsUrl}${API_BASE}/ws/operator`;
}

export function getBrainStatusWebSocketUrl(): string {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const wsUrl = baseUrl.replace(/^http/, 'ws');
  return `${wsUrl}${API_BASE}/ws/brain-status`;
}

