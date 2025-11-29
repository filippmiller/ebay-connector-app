import { apiClient } from './client';
import type { EbayConnectionStatus, EbayLog, EbayConnectLog } from '../types';

export interface AdminEbayEvent {
  id: string;
  created_at: string | null;
  source: string;
  channel: string;
  topic: string | null;
  entity_type: string | null;
  entity_id: string | null;
  ebay_account: string | null;
  event_time: string | null;
  publish_time: string | null;
  status: string;
  error: string | null;
  signature_valid: boolean | null;
  signature_kid: string | null;
  // Preview subset of the raw payload; structure depends on event type.
  payload_preview: any;
}

export interface AdminEbayEventsResponse {
  items: AdminEbayEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface GetAdminEbayEventsParams {
  topic?: string;
  entityType?: string;
  entityId?: string;
  ebayAccount?: string;
  source?: string;
  channel?: string;
  status?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
  sortBy?: 'event_time' | 'created_at';
  sortDir?: 'asc' | 'desc';
}

export interface AdminEbayEventDetail extends AdminEbayEvent {
  headers: any;
  payload: any;
}

export interface NotificationAccountInfo {
  id: string;
  username?: string | null;
  environment?: string | null;
}

export interface NotificationsStatus {
  environment: string;
  webhookUrl: string | null;
  /**
   * True when the primary webhook topic has a healthy destination/subscription and
   * we have seen at least one recent event. False for misconfig, no events, or
   * Notification API errors.
   */
  ok: boolean;
  state: 'ok' | 'no_events' | 'misconfigured';
  reason: string | null;
  destination: any | null;
  subscription: any | null;
  destinationId?: string | null;
  subscriptionId?: string | null;
  destinationStatus?: string | null;
  subscriptionStatus?: string | null;
  verificationStatus?: string | null;
  recentEvents: {
    count: number;
    lastEventTime: string | null;
  };
  checkedAt?: string;
  errorSummary?: string;
  notificationError?: {
    status_code?: number;
    message?: string;
    body?: any;
    [key: string]: any;
  } | null;
  account?: NotificationAccountInfo | null;
  topics?: Array<{
    topicId: string;
    scope?: string | null;
    destinationId?: string | null;
    subscriptionId?: string | null;
    destinationStatus?: string | null;
    subscriptionStatus?: string | null;
    verificationStatus?: string | null;
    tokenType?: 'application' | 'user' | null;
    /** Per-topic derived status flag: 'OK' when dest/sub are enabled, 'ERROR' on Notification API errors. */
    status?: string | null;
    /** Optional human-readable error summary for this topic. */
    error?: string | null;
    recentEvents: {
      count: number;
      lastEventTime: string | null;
    };
  }>;
}

export interface TestNotificationResponse {
  ok: boolean;
  environment: string;
  destinationId?: string;
  subscriptionId?: string;
  message?: string;
  reason?: string;
  webhookUrl?: string;
  errorSummary?: string;
  notificationError?: {
    status_code?: number;
    message?: string;
    body?: any;
    [key: string]: any;
  } | null;
  error?: string;
  logs?: string[];
  account?: NotificationAccountInfo | null;
  topicId?: string;
  tokenType?: 'application' | 'user' | null;
}

export interface EbayTokenStatusAccount {
  account_id: string;
  account_name: string | null;
  ebay_user_id: string | null;
  status: 'ok' | 'expiring_soon' | 'expired' | 'error' | 'not_connected' | 'unknown';
  expires_at: string | null;
  expires_in_seconds: number | null;
  has_refresh_token: boolean;
  last_refresh_at: string | null;
  last_refresh_success: boolean | null;
  last_refresh_error: string | null;
  refresh_failures_in_row: number;
}

export interface EbayTokenStatusResponse {
  accounts: EbayTokenStatusAccount[];
}

export interface TokenRefreshWorkerStatus {
  worker_name: string;
  interval_seconds: number;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_status: string | null;
  last_error_message: string | null;
  runs_ok_in_row: number;
  runs_error_in_row: number;
  next_run_estimated_at: string | null;
}

export interface EbayTokenRefreshLogRow {
  id: string;
  started_at: string | null;
  finished_at: string | null;
  success: boolean | null;
  error_code: string | null;
  error_message: string | null;
  old_expires_at: string | null;
  new_expires_at: string | null;
  triggered_by: string;
}

export interface EbayTokenRefreshLogResponse {
  account: {
    id: string;
    ebay_user_id: string | null;
    house_name: string | null;
  };
  logs: EbayTokenRefreshLogRow[];
}

export const ebayApi = {
  async startAuth(
    redirectUri: string,
    environment: 'sandbox' | 'production' = 'sandbox',
    scopes?: string[],
    houseName?: string,
  ): Promise<{ authorization_url: string; state: string }> {
    const params = new URLSearchParams({ 
      redirect_uri: redirectUri,
      environment: environment,
    });
    if (houseName) {
      params.set('house_name', houseName);
    }
    const body = scopes ? { scopes } : {};
    const response = await apiClient.post(`/ebay/auth/start?${params}`, body);
    return response.data;
  },

  async handleCallback(code: string, redirectUri: string, environment: string = 'sandbox', state?: string): Promise<{ message: string; expires_in: number }> {
    const params = new URLSearchParams({ 
      redirect_uri: redirectUri,
      environment: environment
    });
    const response = await apiClient.post(`/ebay/auth/callback?${params}`, { code, state });
    return response.data;
  },

  async getStatus(): Promise<EbayConnectionStatus> {
    const response = await apiClient.get<EbayConnectionStatus>('/ebay/status');
    return response.data;
  },

  async disconnect(): Promise<{ message: string }> {
    const response = await apiClient.post('/ebay/disconnect');
    return response.data;
  },

  async getLogs(limit: number = 100): Promise<{ logs: EbayLog[]; total: number }> {
    const response = await apiClient.get<{ logs: EbayLog[]; total: number }>(`/ebay/logs?limit=${limit}`);
    return response.data;
  },

  async clearLogs(): Promise<{ message: string }> {
    const response = await apiClient.delete('/ebay/logs');
    return response.data;
  },

  async getConnectLogs(environment?: 'sandbox' | 'production', limit: number = 100): Promise<{ logs: EbayConnectLog[] }> {
    const params = new URLSearchParams();
    if (environment) params.set('environment', environment);
    params.set('limit', String(limit));
    const response = await apiClient.get<{ logs: EbayConnectLog[] }>(`/ebay/connect/logs?${params.toString()}`);
    return response.data;
  },

  async getAvailableScopes(): Promise<{ scopes: { scope: string; grant_type: string; description?: string }[] }> {
    const response = await apiClient.get<{ scopes: { scope: string; grant_type: string; description?: string }[] }>(
      '/ebay/scopes',
    );
    return response.data;
  },

  async testFetchOrders(limit: number = 10): Promise<any> {
    const response = await apiClient.get(`/ebay/test/orders?limit=${limit}`);
    return response.data;
  },

  async testFetchTransactions(limit: number = 10): Promise<any> {
    const response = await apiClient.get(`/ebay/test/transactions?limit=${limit}`);
    return response.data;
  },

  async syncAllOrders(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/orders${params}`);
    return response.data;
  },

  async syncAllTransactions(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/transactions${params}`);
    return response.data;
  },

  async syncAllDisputes(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/disputes${params}`);
    return response.data;
  },

  async syncAllOffers(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/offers${params}`);
    return response.data;
  },

  async syncAllInventory(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/inventory${params}`);
    return response.data;
  },

  async getSyncJobs(limit: number = 10): Promise<any> {
    const response = await apiClient.get(`/ebay/sync/jobs?limit=${limit}`);
    return response.data;
  },

  async getOrders(limit: number = 100, offset: number = 0): Promise<any> {
    const response = await apiClient.get(`/ebay/orders?limit=${limit}&offset=${offset}`);
    return response.data;
  },

  // eBay multi-account support
  async getAccounts(activeOnly: boolean = true): Promise<any[]> {
    const params = new URLSearchParams();
    params.set('active_only', activeOnly ? 'true' : 'false');
    const response = await apiClient.get(`/ebay-accounts?${params.toString()}`);
    return response.data;
  },

  async getAdminEbayEvents(params: GetAdminEbayEventsParams = {}): Promise<AdminEbayEventsResponse> {
    const searchParams = new URLSearchParams();

    if (params.topic) searchParams.set('topic', params.topic);
    if (params.entityType) searchParams.set('entityType', params.entityType);
    if (params.entityId) searchParams.set('entityId', params.entityId);
    if (params.ebayAccount) searchParams.set('ebayAccount', params.ebayAccount);
    if (params.source) searchParams.set('source', params.source);
    if (params.channel) searchParams.set('channel', params.channel);
    if (params.status) searchParams.set('status', params.status);
    if (params.from) searchParams.set('from', params.from);
    if (params.to) searchParams.set('to', params.to);
    if (typeof params.limit === 'number') searchParams.set('limit', String(params.limit));
    if (typeof params.offset === 'number') searchParams.set('offset', String(params.offset));
    if (params.sortBy) searchParams.set('sortBy', params.sortBy);
    if (params.sortDir) searchParams.set('sortDir', params.sortDir);

    const qs = searchParams.toString();
    const response = await apiClient.get<AdminEbayEventsResponse>(
      `/api/admin/ebay-events${qs ? `?${qs}` : ''}`,
    );
    return response.data;
  },

  async getAdminEbayEventDetail(eventId: string): Promise<AdminEbayEventDetail> {
    const response = await apiClient.get<AdminEbayEventDetail>(
      `/api/admin/ebay-events/${encodeURIComponent(eventId)}`,
    );
    return response.data;
  },

  async getNotificationsStatus(): Promise<NotificationsStatus> {
    const response = await apiClient.get<NotificationsStatus>('/api/admin/notifications/status');
    return response.data;
  },

  async testMarketplaceDeletionNotification(): Promise<TestNotificationResponse> {
    const response = await apiClient.post<TestNotificationResponse>(
      '/api/admin/notifications/test-marketplace-deletion',
      {},
    );
    return response.data;
  },

  async testNotificationTopic(topicId: string): Promise<TestNotificationResponse> {
    const response = await apiClient.post<TestNotificationResponse>(
      '/api/admin/notifications/test-topic',
      { topicId },
    );
    return response.data;
  },

  async getEbayTokenStatus(): Promise<EbayTokenStatusResponse> {
    const response = await apiClient.get<EbayTokenStatusResponse>('/api/admin/ebay/tokens/status');
    return response.data;
  },

  async getTokenRefreshWorkerStatus(): Promise<TokenRefreshWorkerStatus> {
    const response = await apiClient.get<TokenRefreshWorkerStatus>('/api/admin/workers/token-refresh/status');
    return response.data;
  },

  async getEbayTokenRefreshLog(accountId: string, limit: number = 50): Promise<EbayTokenRefreshLogResponse> {
    const params = new URLSearchParams();
    params.set('account_id', accountId);
    params.set('limit', String(limit));
    const response = await apiClient.get<EbayTokenRefreshLogResponse>(
      `/api/admin/ebay/tokens/refresh/log?${params.toString()}`,
    );
    return response.data;
  },

  async getAdminTokenHttpLogs(env: string, limit: number = 100): Promise<{ logs: EbayConnectLog[] }> {
    const params = new URLSearchParams();
    params.set('env', env);
    params.set('limit', String(limit));
    const response = await apiClient.get<{ logs: EbayConnectLog[] }>(
      `/api/admin/ebay/tokens/logs?${params.toString()}`,
    );
    return response.data;
  },
};
