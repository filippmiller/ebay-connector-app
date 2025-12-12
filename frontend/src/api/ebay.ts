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

export interface TokenRefreshPreviewResponse {
  method: string;
  url: string;
  headers: Record<string, any>;
  body_form: {
    grant_type: string;
    refresh_token: {
      prefix: string | null;
      suffix: string | null;
      length: number;
      starts_with_v: boolean;
      contains_enc_prefix: boolean;
    };
  };
  account?: {
    id: string;
    house_name?: string | null;
    username?: string | null;
    ebay_user_id?: string | null;
  };
  error?: string;
  message?: string;
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

export interface EbayTokenRefreshDebugHttp {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
}

export interface EbayTokenRefreshDebugResponse {
  account: {
    id: string;
    ebay_user_id: string | null;
    house_name: string | null;
  };
  environment: string;
  success: boolean;
  error: string | null;
  error_description: string | null;
  request: EbayTokenRefreshDebugHttp | null;
  response: {
    status_code: number | null;
    reason: string | null;
    headers: Record<string, string> | null;
    body: string | null;
  } | null;
}

export interface WorkersLoopStatusItem {
  loop_name: string;
  worker_name: string;
  interval_seconds: number;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_success_at: string | null;
  last_status: string | null;
  last_error_message: string | null;
  stale: boolean;
  source: string | null;
}

export interface WorkersLoopStatusResponse {
  loops: WorkersLoopStatusItem[];
}

// Generic admin worker DTOs (starting with inventory MV refresh worker)
export interface AdminWorkerDto {
  worker_key: string;
  display_name: string;
  description?: string | null;
  enabled: boolean;
  interval_seconds: number;
  last_run_at?: string | null;
  last_run_status?: string | null;
  last_run_error?: string | null;
}

export interface AdminWorkerRunOnceResponse {
  status: 'success' | 'error';
  message?: string | null;
}

// Test-listing admin DTOs
export interface TestListingConfigDto {
  debug_enabled: boolean;
  test_inventory_status: string | null;
  max_items_per_run: number;
}

export interface TestListingLogSummaryDto {
  id: number;
  created_at: string;
  inventory_id: number | null;
  parts_detail_id: number | null;
  sku: string | null;
  status: string;
  mode: string;
  account_label: string | null;
  error_message: string | null;
}

export interface TestListingLogListResponseDto {
  items: TestListingLogSummaryDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface TestListingLogDetailDto {
  id: number;
  created_at: string;
  inventory_id: number | null;
  parts_detail_id: number | null;
  sku: string | null;
  status: string;
  mode: string;
  account_label: string | null;
  error_message: string | null;
  summary_json: any | null;
  trace: any | null; // Shape matches WorkerDebugTrace from ebayListingWorker.ts
}

export interface TestListingRunResponseDto {
  log_id: number | null;
  items_selected: number;
  items_processed: number;
  items_success: number;
  items_failed: number;
}

export interface TestListingFieldSourceDto {
  table: string;
  column: string;
}

export interface TestListingFieldHelpDto {
  ebay_expected: string;
  internal_semantics?: string | null;
  lookup_rows?: any | null;
}

export interface TestListingPayloadFieldDto {
  key: string;
  label: string;
  required: boolean;
  value: string | null;
  missing: boolean;
  sources: TestListingFieldSourceDto[];
  help?: TestListingFieldHelpDto | null;
}

export interface TestListingPayloadResponseDto {
  legacy_inventory_id: number;
  sku: string | null;
  legacy_status_code: string | null;
  legacy_status_name: string | null;
  parts_detail_id: number | null;
  mandatory_fields: TestListingPayloadFieldDto[];
  optional_fields: TestListingPayloadFieldDto[];
}

export interface TestListingListRequestDto {
  legacy_inventory_id: number;
  force?: boolean;
}

export interface TestListingPrepareResponseDto {
  legacy_inventory_id: number;
  sku: string;
  account_label?: string | null;
  offer_id?: string | null;
  chosen_offer?: any | null;
  offers_payload?: any | null;
  http_offer_lookup?: any | null;
  http_publish_planned?: any | null;
}

export interface EbayReturnRow {
  return_id: string;
  account_id: string | null;
  ebay_user_id: string | null;
  order_id: string | null;
  item_id: string | null;
  transaction_id: string | null;
  return_state: string | null;
  return_type: string | null;
  reason: string | null;
  buyer_username: string | null;
  seller_username: string | null;
  total_amount_value: number | null;
  total_amount_currency: string | null;
  creation_date: string | null;
  last_modified_date: string | null;
  closed_date: string | null;
}

export interface EbayReturnsResponse {
  items: EbayReturnRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface EbayReturnMessage {
  kind?: string | null;
  author?: string | null;
  activity?: string | null;
  from_state?: string | null;
  to_state?: string | null;
  text: string;
  created_at?: string | null;
}

export interface EbayReturnDetailResponse {
  row: EbayReturnRow;
  messages: EbayReturnMessage[];
  raw: any;
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

  async getTokenRefreshPreview(ebayAccountId: string): Promise<TokenRefreshPreviewResponse> {
    const response = await apiClient.get<TokenRefreshPreviewResponse>(
      `/api/admin/ebay/token/refresh-preview/${encodeURIComponent(ebayAccountId)}`,
    );
    return response.data;
  },

  async getAdminTokenTerminalLogs(
    env: string,
    limit: number = 50,
  ): Promise<{ entries: any[] }> {
    const params = new URLSearchParams();
    params.set('env', env);
    params.set('limit', String(limit));
    const response = await apiClient.get<{ entries: any[] }>(
      `/api/admin/ebay/tokens/terminal-logs?${params.toString()}`,
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

  async debugRefreshToken(accountId: string): Promise<EbayTokenRefreshDebugResponse> {
    const response = await apiClient.post<EbayTokenRefreshDebugResponse>(
      '/api/admin/ebay/token/refresh-debug',
      { ebay_account_id: accountId },
    );
    return response.data;
  },

  async getWorkersLoopStatus(): Promise<WorkersLoopStatusResponse> {
    const response = await apiClient.get<WorkersLoopStatusResponse>('/api/admin/ebay/workers/loop-status');
    return response.data;
  },

  async runEbayWorkersOnce(): Promise<{ status: string }> {
    const response = await apiClient.post<{ status: string }>(
      '/api/admin/ebay/workers/run-once',
    );
    return response.data;
  },

  async runTokenRefreshWorkerOnce(): Promise<{ status: string; count: number; results: any[] }> {
    const response = await apiClient.post<{ status: string; count: number; results: any[] }>(
      '/api/admin/ebay/workers/token-refresh/run-once',
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

  async getReturns(params: {
    accountId: string;
    state?: string;
    dateFrom?: string;
    dateTo?: string;
    limit?: number;
    offset?: number;
  }): Promise<EbayReturnsResponse> {
    const searchParams = new URLSearchParams();
    searchParams.set('account_id', params.accountId);
    if (params.state) searchParams.set('state', params.state);
    if (params.dateFrom) searchParams.set('date_from', params.dateFrom);
    if (params.dateTo) searchParams.set('date_to', params.dateTo);
    if (typeof params.limit === 'number') searchParams.set('limit', String(params.limit));
    if (typeof params.offset === 'number') searchParams.set('offset', String(params.offset));
    const response = await apiClient.get<EbayReturnsResponse>(
      `/ebay/returns?${searchParams.toString()}`,
    );
    return response.data;
  },

  async getReturnDetail(params: { accountId: string; returnId: string }): Promise<EbayReturnDetailResponse> {
    const searchParams = new URLSearchParams();
    searchParams.set('account_id', params.accountId);
    searchParams.set('return_id', params.returnId);
    const response = await apiClient.get<EbayReturnDetailResponse>(
      `/ebay/returns/detail?${searchParams.toString()}`,
    );
    return response.data;
  },

  async getAllWorkerRuns(params?: {
    ebay_account_id?: string;
    api_family?: string;
    status_filter?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ runs: any[]; total: number }> {
    const searchParams = new URLSearchParams();
    if (params?.ebay_account_id) searchParams.set('ebay_account_id', params.ebay_account_id);
    if (params?.api_family) searchParams.set('api_family', params.api_family);
    if (params?.status_filter) searchParams.set('status_filter', params.status_filter);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    const response = await apiClient.get<{ runs: any[]; total: number }>(
      `/ebay/workers/runs/all?${searchParams.toString()}`,
    );
    return response.data;
  },

  async cleanupOldWorkerLogs(daysToKeep: number): Promise<{
    deleted_runs: number;
    deleted_logs: number;
    cutoff_date: string;
    message: string;
  }> {
    const response = await apiClient.delete<{
      deleted_runs: number;
      deleted_logs: number;
      cutoff_date: string;
      message: string;
    }>(`/ebay/workers/logs/cleanup?days_to_keep=${daysToKeep}`);
    return response.data;
  },

  // Admin → Workers: generic background workers (starting with inventory MV refresh)
  async getInventoryMvWorker(): Promise<AdminWorkerDto> {
    const response = await apiClient.get<AdminWorkerDto>(
      '/api/admin/workers/inventory-mv-refresh',
    );
    return response.data;
  },

  async updateInventoryMvWorker(
    payload: Partial<Pick<AdminWorkerDto, 'enabled' | 'interval_seconds'>>,
  ): Promise<AdminWorkerDto> {
    const response = await apiClient.put<AdminWorkerDto>(
      '/api/admin/workers/inventory-mv-refresh',
      payload,
    );
    return response.data;
  },

  async runInventoryMvWorkerOnce(): Promise<AdminWorkerRunOnceResponse> {
    const response = await apiClient.post<AdminWorkerRunOnceResponse>(
      '/api/admin/workers/inventory-mv-refresh/run-once',
      {},
    );
    return response.data;
  },

  // Admin → eBay test-listing UI
  async getTestListingConfig(): Promise<TestListingConfigDto> {
    const response = await apiClient.get<TestListingConfigDto>(
      '/api/admin/ebay/test-listing/config',
    );
    return response.data;
  },

  async updateTestListingConfig(
    payload: Partial<TestListingConfigDto>,
  ): Promise<TestListingConfigDto> {
    const response = await apiClient.put<TestListingConfigDto>(
      '/api/admin/ebay/test-listing/config',
      payload,
    );
    return response.data;
  },

  async runTestListingOnce(limit?: number): Promise<TestListingRunResponseDto> {
    const body: any = {};
    if (typeof limit === 'number') {
      body.limit = limit;
    }
    const response = await apiClient.post<TestListingRunResponseDto>(
      '/api/admin/ebay/test-listing/run',
      body,
    );
    return response.data;
  },

  async getTestListingLogs(params?: {
    limit?: number;
    offset?: number;
    status_filter?: string;
  }): Promise<TestListingLogListResponseDto> {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.status_filter) searchParams.set('status_filter', params.status_filter);
    const qs = searchParams.toString();
    const response = await apiClient.get<TestListingLogListResponseDto>(
      `/api/admin/ebay/test-listing/logs${qs ? `?${qs}` : ''}`,
    );
    return response.data;
  },

  async getTestListingLogDetail(logId: number): Promise<TestListingLogDetailDto> {
    const response = await apiClient.get<TestListingLogDetailDto>(
      `/api/admin/ebay/test-listing/logs/${logId}`,
    );
    return response.data;
  },

  async getTestListingPayloadPreview(
    legacyInventoryId: number,
  ): Promise<TestListingPayloadResponseDto> {
    const response = await apiClient.get<TestListingPayloadResponseDto>(
      `/api/admin/ebay/test-listing/payload?legacy_inventory_id=${encodeURIComponent(String(legacyInventoryId))}`,
    );
    return response.data;
  },

  async listTestListingLegacyInventory(
    payload: TestListingListRequestDto,
  ): Promise<{ trace: any; summary: any }> {
    const response = await apiClient.post<{ trace: any; summary: any }>(
      '/api/admin/ebay/test-listing/list',
      payload,
    );
    return response.data;
  },

  async prepareTestListingLegacyInventory(
    legacyInventoryId: number,
  ): Promise<TestListingPrepareResponseDto> {
    const response = await apiClient.post<TestListingPrepareResponseDto>(
      '/api/admin/ebay/test-listing/prepare',
      { legacy_inventory_id: legacyInventoryId },
    );
    return response.data;
  },
};
