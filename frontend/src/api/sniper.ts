import api from '@/lib/apiClient';

export interface SnipeRow {
  id: string;
  user_id: string;
  ebay_account_id: string | null;
  item_id: string;
  title: string | null;
  image_url: string | null;
  end_time: string | null;
  fire_at: string | null;
  max_bid_amount: number | null;
  currency: string | null;
  seconds_before_end: number | null;
  status: string | null;
  has_bid?: boolean | null;
  current_bid_at_creation: number | null;
  result_price: number | null;
  result_message: string | null;
  comment: string | null;
  contingency_group_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SnipesListResponse {
  rows: SnipeRow[];
  limit: number;
  offset: number;
  total: number;
}

export interface ListSnipesParams {
  limit?: number;
  offset?: number;
  status?: string;
  ebay_account_id?: string;
  search?: string;
}

export interface CreateSnipePayload {
  ebay_account_id: string;
  item_id: string;
  max_bid_amount: number;
  seconds_before_end?: number;
  comment?: string;
}

export interface UpdateSnipePayload {
  max_bid_amount?: number;
  seconds_before_end?: number;
  comment?: string;
  status?: string; // e.g. 'cancelled'
}

export interface SnipeLogRow {
  id: string;
  created_at: string | null;
  event_type: string;
  status: string | null;
  message: string | null;
  ebay_bid_id: string | null;
  correlation_id: string | null;
  http_status: number | null;
}

export interface SnipeLogsResponse {
  snipe_id: string;
  logs: SnipeLogRow[];
}

export async function listSnipes(params: ListSnipesParams = {}): Promise<SnipesListResponse> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set('limit', String(params.limit));
  if (params.offset != null) search.set('offset', String(params.offset));
  if (params.status) search.set('status', params.status);
  if (params.ebay_account_id) search.set('ebay_account_id', params.ebay_account_id);
  if (params.search) search.set('search', params.search);

  const resp = await api.get<SnipesListResponse>(`/api/sniper/snipes?${search.toString()}`);
  return resp.data;
}

export async function createSnipe(payload: CreateSnipePayload): Promise<SnipeRow> {
  const resp = await api.post<SnipeRow>('/api/sniper/snipes', payload);
  return resp.data;
}

export async function updateSnipe(id: string, payload: UpdateSnipePayload): Promise<SnipeRow> {
  const resp = await api.patch<SnipeRow>(`/api/sniper/snipes/${id}`, payload);
  return resp.data;
}

export async function cancelSnipe(id: string): Promise<SnipeRow> {
  const resp = await api.delete<SnipeRow>(`/api/sniper/snipes/${id}`);
  return resp.data;
}

export async function getSnipeLogs(id: string): Promise<SnipeLogsResponse> {
  const resp = await api.get<SnipeLogsResponse>(`/api/sniper/snipes/${id}/logs`);
  return resp.data;
}
