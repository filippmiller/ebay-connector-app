import apiClient from './client';

export interface TimesheetEntry {
  id: number;
  userId: string;
  username: string;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number | null;
  rate: string | null;
  description: string | null;
  deleteFlag: boolean;
  recordCreated: string;
  recordCreatedBy: string | null;
  recordUpdated: string;
  recordUpdatedBy: string | null;
  legacyId: number | null;
}

export interface Pagination<T> {
  items: T[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  } | null;
}

export async function startTimesheet(description?: string): Promise<Envelope<TimesheetEntry>> {
  const resp = await apiClient.post('/api/timesheets/start', { description: description ?? null });
  return resp.data;
}

export async function stopTimesheet(description?: string): Promise<Envelope<TimesheetEntry>> {
  const resp = await apiClient.post('/api/timesheets/stop', { description: description ?? null });
  return resp.data;
}

export async function getMyTimesheets(params: {
  from?: string;
  to?: string;
  page?: number;
  pageSize?: number;
} = {}): Promise<Envelope<Pagination<TimesheetEntry>>> {
  const search = new URLSearchParams();
  if (params.from) search.set('from', params.from);
  if (params.to) search.set('to', params.to);
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('pageSize', String(params.pageSize));

  const resp = await apiClient.get(`/api/timesheets/my?${search.toString()}`);
  return resp.data;
}

export async function adminListTimesheets(params: {
  userId?: string;
  username?: string;
  from?: string;
  to?: string;
  page?: number;
  pageSize?: number;
} = {}): Promise<Envelope<Pagination<TimesheetEntry>>> {
  const search = new URLSearchParams();
  if (params.userId) search.set('userId', params.userId);
  if (params.username) search.set('username', params.username);
  if (params.from) search.set('from', params.from);
  if (params.to) search.set('to', params.to);
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('pageSize', String(params.pageSize));

  const resp = await apiClient.get(`/api/timesheets?${search.toString()}`);
  return resp.data;
}

export async function adminAddTimesheet(payload: {
  userId: string;
  startTime: string;
  endTime: string;
  rate?: string;
  description?: string;
}): Promise<Envelope<TimesheetEntry>> {
  const resp = await apiClient.post('/api/timesheets/admin/add', payload);
  return resp.data;
}

export async function adminPatchTimesheet(
  id: number,
  payload: {
    startTime?: string;
    endTime?: string;
    rate?: string;
    description?: string;
    deleteFlag?: boolean;
  }
): Promise<Envelope<TimesheetEntry>> {
  const resp = await apiClient.patch(`/api/timesheets/admin/${id}`, payload);
  return resp.data;
}
