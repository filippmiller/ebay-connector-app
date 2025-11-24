import { apiClient } from './client';

export interface SecuritySettingsDto {
  id: number;
  max_failed_attempts: number;
  initial_block_minutes: number;
  progressive_delay_step_minutes: number;
  max_delay_minutes: number;
  enable_captcha: boolean;
  captcha_after_failures: number;
  session_ttl_minutes: number;
  session_idle_timeout_minutes: number;
  bruteforce_alert_threshold_per_ip: number;
  bruteforce_alert_threshold_per_user: number;
  alert_email_enabled: boolean;
  alert_channel: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SecuritySettingsResponse {
  id: number;
  max_failed_attempts: number;
  initial_block_minutes: number;
  progressive_delay_step_minutes: number;
  max_delay_minutes: number;
  enable_captcha: boolean;
  captcha_after_failures: number;
  session_ttl_minutes: number;
  session_idle_timeout_minutes: number;
  bruteforce_alert_threshold_per_ip: number;
  bruteforce_alert_threshold_per_user: number;
  alert_email_enabled: boolean;
  alert_channel: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SecuritySettingsUpdateResponse {
  ok: boolean;
  settings: SecuritySettingsResponse;
}

export interface SecurityEventDto {
  id: string;
  created_at: string | null;
  user_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  event_type: string;
  description: string | null;
  metadata: Record<string, unknown>;
}

export interface SecurityEventsListResponse {
  items: SecurityEventDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface SecurityOverviewResponse {
  window_hours: number;
  from: string;
  to: string;
  metrics: {
    login_success: number;
    login_failed: number;
    login_blocked: number;
    settings_changed: number;
    security_alert: number;
  };
  top_failed_ips: Array<{
    ip_address: string;
    count: number;
  }>;
}

export interface GetSecurityEventsParams {
  event_type?: string;
  user_id?: string;
  ip?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export const securityApi = {
  async getSettings(): Promise<SecuritySettingsResponse> {
    const resp = await apiClient.get<SecuritySettingsResponse>('/api/admin/security/settings');
    return resp.data;
  },

  async updateSettings(payload: Partial<SecuritySettingsResponse>): Promise<SecuritySettingsUpdateResponse> {
    const resp = await apiClient.put<SecuritySettingsUpdateResponse>(
      '/api/admin/security/settings',
      payload,
    );
    return resp.data;
  },

  async getEvents(params: GetSecurityEventsParams = {}): Promise<SecurityEventsListResponse> {
    const search = new URLSearchParams();
    if (params.event_type) search.set('event_type', params.event_type);
    if (params.user_id) search.set('user_id', params.user_id);
    if (params.ip) search.set('ip', params.ip);
    if (params.from) search.set('from', params.from);
    if (params.to) search.set('to', params.to);
    if (typeof params.limit === 'number') search.set('limit', String(params.limit));
    if (typeof params.offset === 'number') search.set('offset', String(params.offset));

    const qs = search.toString();
    const resp = await apiClient.get<SecurityEventsListResponse>(
      `/api/admin/security/events${qs ? `?${qs}` : ''}`,
    );
    return resp.data;
  },

  async exportEvents(params: GetSecurityEventsParams = {}): Promise<{ rows: SecurityEventDto[] }> {
    const search = new URLSearchParams();
    if (params.event_type) search.set('event_type', params.event_type);
    if (params.user_id) search.set('user_id', params.user_id);
    if (params.ip) search.set('ip', params.ip);
    if (params.from) search.set('from', params.from);
    if (params.to) search.set('to', params.to);

    const qs = search.toString();
    const resp = await apiClient.get<{ rows: SecurityEventDto[] }>(
      `/api/admin/security/events/export${qs ? `?${qs}` : ''}`,
    );
    return resp.data;
  },

  async getOverview(window_hours: number = 24): Promise<SecurityOverviewResponse> {
    const search = new URLSearchParams();
    if (window_hours) search.set('window_hours', String(window_hours));
    const qs = search.toString();
    const resp = await apiClient.get<SecurityOverviewResponse>(
      `/api/admin/security/overview${qs ? `?${qs}` : ''}`,
    );
    return resp.data;
  },
};
