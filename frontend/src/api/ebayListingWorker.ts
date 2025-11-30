import { apiClient } from './client';

export type WorkerDebugStepType =
  | 'info'
  | 'db-select'
  | 'db-update'
  | 'log-insert'
  | 'ebay-request'
  | 'ebay-response'
  | 'error';

export interface WorkerDebugHttp {
  method: string;
  url: string;
  headers: Record<string, any>;
  body?: any;
  status_code?: number | null;
  duration_ms?: number | null;
}

export interface ColumnChange {
  old: any | null;
  new: any | null;
}

export interface WorkerDebugDbChange {
  table_name: 'parts_detail' | 'parts_detail_log';
  row_id: number;
  changes: Record<string, ColumnChange>;
}

export interface WorkerDebugStep {
  timestamp: string; // ISO string from backend
  type: WorkerDebugStepType;
  label?: string | null;
  message: string;
  http?: WorkerDebugHttp | null;
  db_change?: WorkerDebugDbChange | null;
  extra?: Record<string, any>;
}

export interface WorkerDebugTrace {
  job_id: string;
  account?: string | null;
  items_count: number;
  steps: WorkerDebugStep[];
}

export interface EbayListingDebugSummaryAccount {
  username: string | null;
  ebay_id: string | null;
  items: number;
  success: number;
  failed: number;
}

export interface EbayListingDebugSummary {
  items_selected: number;
  items_processed: number;
  items_success: number;
  items_failed: number;
  accounts: EbayListingDebugSummaryAccount[];
}

export interface EbayListingDebugRequest {
  ids?: number[];
  dry_run?: boolean;
  max_items?: number;
}

export interface EbayListingDebugResponse {
  trace: WorkerDebugTrace;
  summary: EbayListingDebugSummary;
}

export async function runEbayListingDebug(
  payload: EbayListingDebugRequest,
): Promise<EbayListingDebugResponse> {
  const response = await apiClient.post<EbayListingDebugResponse>(
    '/api/debug/ebay/list-once',
    payload,
  );
  return response.data;
}
