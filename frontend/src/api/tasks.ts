import apiClient from './client';

export interface TaskListItem {
  id: string;
  type: 'task' | 'reminder';
  title: string;
  description?: string | null;
  status: string;
  priority: string;
  due_at?: string | null;
  snooze_until?: string | null;
  is_popup: boolean;
  creator_id: string;
  creator_username?: string | null;
  assignee_id?: string | null;
  assignee_username?: string | null;
  comment_count: number;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  items: TaskListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaskComment {
  id: string;
  task_id: string;
  author_id?: string | null;
  author_name?: string | null;
  body: string;
  kind: string;
  created_at: string;
}

export interface TaskDetail extends TaskListItem {
  completed_at?: string | null;
  comments: TaskComment[];
}

export interface TaskCreatePayload {
  type: 'task' | 'reminder';
  title: string;
  description?: string;
  assignee_id?: string;
  due_at?: string;
  is_popup?: boolean;
  priority?: 'low' | 'normal' | 'high';
}

export interface TaskUpdatePayload {
  title?: string;
  description?: string;
  assignee_id?: string;
  due_at?: string;
  is_popup?: boolean;
  priority?: 'low' | 'normal' | 'high';
}

export interface TaskStatusChangePayload {
  new_status: string;
  comment?: string;
}

export interface TaskSnoozePayload {
  snooze_until?: string;
  preset?: '15m' | '1h' | 'tomorrow';
}

export interface TaskNotificationTaskSummary {
  id: string;
  type?: 'task' | 'reminder';
  title?: string;
  status?: string;
  priority?: string;
  due_at?: string | null;
  creator_id?: string;
  creator_username?: string | null;
  assignee_id?: string | null;
  assignee_username?: string | null;
}

export interface TaskNotificationItem {
  id: string;
  task_id: string;
  user_id: string;
  kind: 'task_assigned' | 'task_status_changed' | 'task_comment_added' | 'reminder_fired' | string;
  status: 'unread' | 'read' | 'dismissed' | string;
  created_at: string;
  read_at?: string | null;
  dismissed_at?: string | null;
  task: TaskNotificationTaskSummary;
}

export interface TaskNotificationsListResponse {
  items: TaskNotificationItem[];
}

export interface GetTasksOptions {
  type?: 'task' | 'reminder';
  role?: 'assigned_to_me' | 'created_by_me' | 'all';
  status?: string[];
  search?: string;
  page?: number;
  pageSize?: number;
}

export const getTasks = async (options: GetTasksOptions = {}): Promise<TaskListResponse> => {
  const {
    type,
    role = 'assigned_to_me',
    status,
    search,
    page = 1,
    pageSize = 50,
  } = options;

  const params = new URLSearchParams({
    role,
    page: String(page),
    page_size: String(pageSize),
  });

  if (type) {
    params.append('type', type);
  }
  if (status && status.length) {
    status.forEach((s) => params.append('status', s));
  }
  if (search) {
    params.append('search', search);
  }

  const resp = await apiClient.get(`/api/tasks?${params.toString()}`);
  return resp.data as TaskListResponse;
};

export const getTask = async (taskId: string): Promise<TaskDetail> => {
  const resp = await apiClient.get(`/api/tasks/${taskId}`);
  return resp.data as TaskDetail;
};

export const createTask = async (payload: TaskCreatePayload): Promise<TaskDetail> => {
  const resp = await apiClient.post('/api/tasks', payload);
  return resp.data as TaskDetail;
};

export const updateTask = async (taskId: string, payload: TaskUpdatePayload): Promise<TaskDetail> => {
  const resp = await apiClient.patch(`/api/tasks/${taskId}`, payload);
  return resp.data as TaskDetail;
};

export const changeTaskStatus = async (
  taskId: string,
  payload: TaskStatusChangePayload,
): Promise<TaskDetail> => {
  const resp = await apiClient.post(`/api/tasks/${taskId}/status`, payload);
  return resp.data as TaskDetail;
};

export const addTaskComment = async (
  taskId: string,
  body: string,
): Promise<TaskDetail> => {
  const resp = await apiClient.post(`/api/tasks/${taskId}/comments`, { body });
  return resp.data as TaskDetail;
};

export const snoozeTask = async (
  taskId: string,
  payload: TaskSnoozePayload,
): Promise<TaskDetail> => {
  const resp = await apiClient.post(`/api/tasks/${taskId}/snooze`, payload);
  return resp.data as TaskDetail;
};

export const getUnreadTaskNotifications = async (
  since?: string,
): Promise<TaskNotificationsListResponse> => {
  const params = new URLSearchParams();
  if (since) {
    params.append('since', since);
  }
  const query = params.toString();
  const url = query ? `/api/task-notifications/unread?${query}` : '/api/task-notifications/unread';
  const resp = await apiClient.get(url);
  return resp.data as TaskNotificationsListResponse;
};

export const markTaskNotificationRead = async (notificationId: string): Promise<void> => {
  await apiClient.post(`/api/task-notifications/${notificationId}/read`);
};

export const dismissTaskNotification = async (notificationId: string): Promise<void> => {
  await apiClient.post(`/api/task-notifications/${notificationId}/dismiss`);
};
