import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Plus, Search, LayoutList, LayoutPanelLeft, Check, Clock, X, Play, Flag, Archive, Trash2 } from 'lucide-react';

import FixedHeader from '@/components/FixedHeader';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  TaskDetail,
  TaskListItem,
  TaskCreatePayload,
  TaskSnoozePayload,
  getTasks,
  getTask,
  createTask,
  changeTaskStatus,
  addTaskComment,
  snoozeTask,
  archiveTask,
  unarchiveTask,
  setTaskImportant,
  deleteTask,
} from '@/api/tasks';
import { useAuth } from '@/contexts/AuthContext';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';


type ViewMode = 'list' | 'board';

type TypeFilter = 'all' | 'task' | 'reminder';

type RoleFilter = 'assigned_to_me' | 'created_by_me' | 'all';

const TASK_STATUS_COLORS: Record<string, string> = {
  new: 'bg-gray-100 text-gray-800',
  in_progress: 'bg-blue-100 text-blue-800',
  snoozed: 'bg-amber-100 text-amber-800',
  done: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
  scheduled: 'bg-gray-100 text-gray-800',
  fired: 'bg-blue-100 text-blue-800',
  dismissed: 'bg-gray-100 text-gray-500',
};

const PRIORITY_COLORS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-700',
  normal: 'bg-slate-100 text-slate-800',
  high: 'bg-red-100 text-red-800',
};

const TasksPage: React.FC = () => {
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('assigned_to_me');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [total, setTotal] = useState(0);

  const [selectedTask, setSelectedTask] = useState<TaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createPayload, setCreatePayload] = useState<TaskCreatePayload>({
    type: 'task',
    title: '',
    description: '',
    priority: 'normal',
    is_popup: true,
  });
  const [creating, setCreating] = useState(false);

  const [newComment, setNewComment] = useState('');
  const [updatingStatus, setUpdatingStatus] = useState(false);

  const queryTaskId = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('taskId');
  }, [location.search]);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getTasks({
        type: typeFilter === 'all' ? undefined : typeFilter,
        role: roleFilter,
        status: statusFilter ? [statusFilter] : undefined,
        search: searchQuery || undefined,
        page,
        pageSize,
        archived: showArchived,
      });
      setTasks(resp.items || []);
      setTotal(resp.total || 0);
    } catch (e: any) {
      console.error('Failed to load tasks', e);
      const message = e?.response?.data?.detail || e.message || 'Failed to load tasks';
      setError(message);
      setTasks([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, roleFilter, statusFilter, searchQuery, page, pageSize, showArchived]);

  const loadTaskDetail = useCallback(async (taskId: string) => {
    setDetailLoading(true);
    try {
      const detail = await getTask(taskId);
      setSelectedTask(detail);
    } catch (e: any) {
      console.error('Failed to load task detail', e);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    if (queryTaskId) {
      void loadTaskDetail(queryTaskId);
    }
  }, [queryTaskId, loadTaskDetail]);

  const handleOpenTask = (task: TaskListItem) => {
    void loadTaskDetail(task.id);
  };

  const handleCreateTask = async () => {
    if (!createPayload.title.trim()) return;
    setCreating(true);
    try {
      const created = await createTask(createPayload);
      setCreateOpen(false);
      setCreatePayload({
        type: 'task',
        title: '',
        description: '',
        priority: 'normal',
        is_popup: true,
      });
      await loadTasks();
      setSelectedTask(created);
    } catch (e: any) {
      console.error('Failed to create task', e);
    } finally {
      setCreating(false);
    }
  };

  const handleStatusChange = async (taskId: string, newStatus: string, comment?: string) => {
    setUpdatingStatus(true);
    try {
      const updated = await changeTaskStatus(taskId, { new_status: newStatus, comment });
      setSelectedTask(updated);
      await loadTasks();
    } catch (e: any) {
      console.error('Failed to update status', e);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleAddComment = async () => {
    if (!selectedTask || !newComment.trim()) return;
    try {
      const updated = await addTaskComment(selectedTask.id, newComment.trim());
      setSelectedTask(updated);
      setNewComment('');
    } catch (e: any) {
      console.error('Failed to add comment', e);
    }
  };

  const handleSnooze = async (taskId: string, payload: TaskSnoozePayload) => {
    setUpdatingStatus(true);
    try {
      const updated = await snoozeTask(taskId, payload);
      setSelectedTask(updated);
      await loadTasks();
    } catch (e: any) {
      console.error('Failed to snooze task', e);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const groupedForBoard = useMemo(() => {
    const onlyTasks = tasks.filter((t) => t.type === 'task');
    const groups: Record<string, TaskListItem[]> = {
      new: [],
      in_progress: [],
      snoozed: [],
      done: [],
    };
    for (const t of onlyTasks) {
      const key = (t.status || 'new').toLowerCase();
      if (!groups[key]) groups[key] = [];
      groups[key].push(t);
    }
    return groups;
  }, [tasks]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const renderStatusBadge = (task: TaskListItem | TaskDetail) => {
    const status = (task.status || '').toLowerCase();
    const color = TASK_STATUS_COLORS[status] || 'bg-gray-100 text-gray-800';
    return <Badge className={color}>{status || 'unknown'}</Badge>;
  };

  const renderPriorityBadge = (task: TaskListItem | TaskDetail) => {
    const priority = (task.priority || 'normal').toLowerCase();
    const color = PRIORITY_COLORS[priority] || PRIORITY_COLORS.normal;
    return <Badge className={color}>{priority}</Badge>;
  };

  const handleArchiveToggle = async (task: TaskListItem | TaskDetail) => {
    try {
      if (task.is_archived) {
        await unarchiveTask(task.id);
      } else {
        await archiveTask(task.id);
      }
      await loadTasks();
      if (selectedTask && selectedTask.id === task.id) {
        const updated = await getTask(task.id).catch(() => null);
        if (updated) setSelectedTask(updated);
      }
    } catch (e) {
      console.error('Failed to toggle archive', e);
    }
  };

  const handleImportantToggle = async (task: TaskListItem | TaskDetail) => {
    try {
      const updated = await setTaskImportant(task.id, !task.is_important);
      await loadTasks();
      if (selectedTask && selectedTask.id === task.id) {
        setSelectedTask(updated);
      }
    } catch (e) {
      console.error('Failed to toggle important', e);
    }
  };

  const handleDelete = async (task: TaskListItem | TaskDetail) => {
    if (task.is_important) return;
    const confirmed = window.confirm('Delete this task permanently? This cannot be undone.');
    if (!confirmed) return;
    try {
      await deleteTask(task.id);
      await loadTasks();
      if (selectedTask && selectedTask.id === task.id) {
        setSelectedTask(null);
      }
    } catch (e: any) {
      console.error('Failed to delete task', e);
      alert(e?.response?.data?.detail || 'Failed to delete task');
    }
  };

  return (
    <div className="h-screen flex flex-col bg-white tasks-page-large-text">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-4 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-2xl font-bold">Tasks & Reminders</h1>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-1" /> New
            </Button>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <div className="flex items-center gap-1 text-xs">
              <span className="font-semibold text-gray-600 mr-1">Type:</span>
              <Button
                size="sm"
                variant={typeFilter === 'all' ? 'default' : 'outline'}
                onClick={() => setTypeFilter('all')}
              >
                All
              </Button>
              <Button
                size="sm"
                variant={typeFilter === 'task' ? 'default' : 'outline'}
                onClick={() => setTypeFilter('task')}
              >
                Tasks
              </Button>
              <Button
                size="sm"
                variant={typeFilter === 'reminder' ? 'default' : 'outline'}
                onClick={() => setTypeFilter('reminder')}
              >
                Reminders
              </Button>
            </div>

            <div className="flex items-center gap-1 text-xs">
              <span className="font-semibold text-gray-600 mr-1">Role:</span>
              <Button
                size="sm"
                variant={roleFilter === 'assigned_to_me' ? 'default' : 'outline'}
                onClick={() => setRoleFilter('assigned_to_me')}
              >
                Assigned to me
              </Button>
              <Button
                size="sm"
                variant={roleFilter === 'created_by_me' ? 'default' : 'outline'}
                onClick={() => setRoleFilter('created_by_me')}
              >
                Created by me
              </Button>
              {isAdmin && (
                <Button
                  size="sm"
                  variant={roleFilter === 'all' ? 'default' : 'outline'}
                  onClick={() => setRoleFilter('all')}
                >
                  All
                </Button>
              )}
            </div>

            <div className="flex items-center gap-1 text-xs">
              <span className="font-semibold text-gray-600 mr-1">Status:</span>
              <select
                className="border rounded px-2 py-1 text-xs"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All</option>
                <option value="new">New</option>
                <option value="in_progress">In progress</option>
                <option value="snoozed">Snoozed</option>
                <option value="done">Done</option>
                <option value="cancelled">Cancelled</option>
                <option value="scheduled">Scheduled</option>
                <option value="fired">Fired</option>
                <option value="dismissed">Dismissed</option>
              </select>
            </div>

            <div className="flex items-center gap-1 text-xs">
              <span className="font-semibold text-gray-600 mr-1">View:</span>
              <Button
                size="sm"
                variant={!showArchived ? 'default' : 'outline'}
                onClick={() => {
                  setShowArchived(false);
                  setPage(1);
                }}
              >
                Active
              </Button>
              <Button
                size="sm"
                variant={showArchived ? 'default' : 'outline'}
                onClick={() => {
                  setShowArchived(true);
                  setPage(1);
                }}
              >
                Archive
              </Button>
            </div>

            <div className="flex-1 min-w-[180px] relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
              <Input
                placeholder="Search title or description..."
                className="pl-7 h-8 text-xs"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
              />
            </div>

            <div className="flex items-center gap-1 ml-auto text-xs">
              <Button
                size="sm"
                variant={viewMode === 'list' ? 'default' : 'outline'}
                onClick={() => setViewMode('list')}
              >
                <LayoutList className="h-3 w-3 mr-1" /> List
              </Button>
              <Button
                size="sm"
                variant={viewMode === 'board' ? 'default' : 'outline'}
                onClick={() => setViewMode('board')}
              >
                <LayoutPanelLeft className="h-3 w-3 mr-1" /> Board
              </Button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 flex gap-4 overflow-hidden">
            <div className="flex-1 overflow-auto border rounded-md bg-white">
              {loading ? (
                <div className="p-4 text-xs text-gray-500">Loading tasks...</div>
              ) : error ? (
                <div className="p-4 text-xs text-red-600">{error}</div>
              ) : viewMode === 'list' ? (
                <table className="min-w-full text-xs">
                  <thead className="bg-gray-50 border-b text-[11px] uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-3 py-2 text-left">Type</th>
                      <th className="px-3 py-2 text-left">Title</th>
                      <th className="px-3 py-2 text-left">From</th>
                      <th className="px-3 py-2 text-left">To</th>
                      <th className="px-3 py-2 text-left">Status</th>
                      <th className="px-3 py-2 text-left">Priority</th>
                      <th className="px-3 py-2 text-left">Due</th>
                      <th className="px-3 py-2 text-left">Created</th>
                      <th className="px-3 py-2 text-left">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="px-3 py-4 text-center text-xs text-gray-500">
                          No tasks found.
                        </td>
                      </tr>
                    ) : (
                      tasks.map((t) => (
                        <tr
                          key={t.id}
                          className="border-b hover:bg-gray-50 cursor-pointer"
                          onClick={() => handleOpenTask(t)}
                        >
                          <td className="px-3 py-2 align-top text-[11px] text-gray-500">
                            {t.type === 'task' ? 'Task' : 'Reminder'}
                          </td>
                          <td className="px-3 py-2 align-top max-w-xs">
                            <div className="flex items-center gap-1">
                              {t.is_important && <Flag className="h-3 w-3 text-red-500 flex-shrink-0" />}
                              <div className="font-semibold text-gray-800 truncate">{t.title}</div>
                            </div>
                            {t.description && (
                              <div className="text-[11px] text-gray-500 truncate">{t.description}</div>
                            )}
                          </td>
                          <td className="px-3 py-2 align-top text-[11px] text-gray-600">
                            {t.creator_username || t.creator_id}
                          </td>
                          <td className="px-3 py-2 align-top text-[11px] text-gray-600">
                            {t.assignee_username || t.assignee_id || '-'}
                          </td>
                          <td className="px-3 py-2 align-top">{renderStatusBadge(t)}</td>
                          <td className="px-3 py-2 align-top">{renderPriorityBadge(t)}</td>
                          <td className="px-3 py-2 align-top text-[11px] text-gray-600">
                            {t.due_at ? new Date(t.due_at).toLocaleString() : '-'}
                          </td>
                          <td className="px-3 py-2 align-top text-[11px] text-gray-500">
                            {new Date(t.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-3 py-2 align-top text-[11px] text-gray-600">
                            <div className="flex flex-wrap gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleArchiveToggle(t);
                                }}
                              >
                                <Archive className="h-3 w-3 mr-1" />
                                {t.is_archived ? 'Unarchive' : 'Archive'}
                              </Button>
                              <Button
                                size="sm"
                                variant={t.is_important ? 'default' : 'outline'}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleImportantToggle(t);
                                }}
                              >
                                <Flag className="h-3 w-3 mr-1" />
                                {t.is_important ? 'Important' : 'Mark important'}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={t.is_important}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleDelete(t);
                                }}
                              >
                                <Trash2 className="h-3 w-3 mr-1" /> Delete
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              ) : (
                // Simple Kanban-style board for tasks only
                <div className="flex gap-3 p-2 overflow-x-auto text-xs">
                  {['new', 'in_progress', 'snoozed', 'done'].map((column) => (
                    <div key={column} className="min-w-[220px] flex-1 bg-gray-50 rounded-md flex flex-col">
                      <div className="px-3 py-2 border-b flex items-center justify-between">
                        <span className="uppercase tracking-wide text-[11px] text-gray-600 font-semibold">
                          {column.replace('_', ' ')}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {groupedForBoard[column]?.length || 0}
                        </Badge>
                      </div>
                      <div className="flex-1 p-2 space-y-2 overflow-y-auto">
                        {(groupedForBoard[column] || []).map((t) => (
                          <div
                            key={t.id}
                            className="bg-white border border-gray-200 rounded-md p-2 shadow-sm cursor-pointer hover:border-blue-300"
                            onClick={() => handleOpenTask(t)}
                          >
                            <div className="font-semibold text-gray-800 text-[13px] truncate mb-1">
                              {t.title}
                            </div>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[10px] text-gray-500 truncate max-w-[110px]">
                                {t.assignee_username || t.assignee_id || '-'}
                              </span>
                              {renderPriorityBadge(t)}
                            </div>
                            {t.due_at && (
                              <div className="text-[10px] text-gray-500 flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {new Date(t.due_at).toLocaleDateString()}
                              </div>
                            )}
                          </div>
                        ))}
                        {(!groupedForBoard[column] || groupedForBoard[column].length === 0) && (
                          <div className="text-[11px] text-gray-400 text-center py-4">No tasks</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Pagination for list view */}
              {viewMode === 'list' && totalPages > 1 && (
                <div className="flex items-center justify-between px-3 py-2 border-t text-[11px] bg-gray-50">
                  <span className="text-gray-500">
                    Page {page} of {totalPages} • {total} items
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Prev
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* Detail panel */}
            <div className="w-[360px] border rounded-md bg-white flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700">Details</span>
                {selectedTask && (
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setSelectedTask(null)}>
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>
              <div className="flex-1 overflow-auto p-3 text-xs">
                {detailLoading ? (
                  <div className="text-gray-500">Loading task...</div>
                ) : !selectedTask ? (
                  <div className="text-gray-400">Select a task to see details</div>
                ) : (
                  <>
                    <div className="mb-2">
                      <div className="flex items-center justify-between mb-1">
                        <Badge variant="outline" className="text-[10px]">
                          {selectedTask.type === 'task' ? 'TASK' : 'REMINDER'}
                        </Badge>
                        <div className="flex items-center gap-1">
                          {selectedTask.is_important && (
                            <span className="inline-flex items-center text-[10px] text-red-600 mr-1">
                              <Flag className="h-3 w-3 mr-0.5" /> Important
                            </span>
                          )}
                          {renderStatusBadge(selectedTask)}
                          {renderPriorityBadge(selectedTask)}
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-gray-900 mb-1">{selectedTask.title}</div>
                      {selectedTask.description && (
                        <div className="text-xs text-gray-700 whitespace-pre-line mb-1">
                          {selectedTask.description}
                        </div>
                      )}
                      <div className="text-[11px] text-gray-500 space-y-0.5 mt-1">
                        <div>
                          <span className="font-semibold">From:</span> {selectedTask.creator_username || selectedTask.creator_id}
                        </div>
                        <div>
                          <span className="font-semibold">To:</span> {selectedTask.assignee_username || selectedTask.assignee_id || '-'}
                        </div>
                        <div>
                          <span className="font-semibold">Due:</span>{' '}
                          {selectedTask.due_at ? new Date(selectedTask.due_at).toLocaleString() : '-'}
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-wrap gap-1 mb-3">
                      {selectedTask.type === 'task' && (
                        <>
                          {(selectedTask.status === 'new' || selectedTask.status === 'snoozed') && (
                          <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleStatusChange(selectedTask.id, 'in_progress')}
                            >
                              <Play className="h-3 w-3 mr-1" /> Start
                            </Button>
                          )}
                          {selectedTask.status !== 'done' && selectedTask.status !== 'cancelled' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleStatusChange(selectedTask.id, 'done')}
                            >
                              <Check className="h-3 w-3 mr-1" /> Done
                            </Button>
                          )}
                          {selectedTask.status !== 'done' && selectedTask.status !== 'cancelled' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleSnooze(selectedTask.id, { preset: '1h' })}
                            >
                              <Clock className="h-3 w-3 mr-1" /> Snooze 1h
                            </Button>
                          )}
                          {selectedTask.status !== 'cancelled' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleStatusChange(selectedTask.id, 'cancelled')}
                            >
                              <X className="h-3 w-3 mr-1" /> Cancel
                            </Button>
                          )}
                        </>
                      )}
                      {selectedTask.type === 'reminder' && (
                        <>
                          {selectedTask.status !== 'done' && selectedTask.status !== 'dismissed' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleStatusChange(selectedTask.id, 'done')}
                            >
                              <Check className="h-3 w-3 mr-1" /> Done
                            </Button>
                          )}
                          {selectedTask.status !== 'done' && selectedTask.status !== 'dismissed' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleSnooze(selectedTask.id, { preset: '1h' })}
                            >
                              <Clock className="h-3 w-3 mr-1" /> Snooze 1h
                            </Button>
                          )}
                          {selectedTask.status !== 'dismissed' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={updatingStatus}
                              onClick={() => handleStatusChange(selectedTask.id, 'dismissed')}
                            >
                              <X className="h-3 w-3 mr-1" /> Dismiss
                            </Button>
                          )}
                        </>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleArchiveToggle(selectedTask)}
                      >
                        <Archive className="h-3 w-3 mr-1" />
                        {selectedTask.is_archived ? 'Unarchive' : 'Archive'}
                      </Button>
                      <Button
                        size="sm"
                        variant={selectedTask.is_important ? 'default' : 'outline'}
                        onClick={() => void handleImportantToggle(selectedTask)}
                      >
                        <Flag className="h-3 w-3 mr-1" />
                        {selectedTask.is_important ? 'Important' : 'Mark important'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={selectedTask.is_important}
                        onClick={() => void handleDelete(selectedTask)}
                      >
                        <Trash2 className="h-3 w-3 mr-1" /> Delete
                      </Button>
                    </div>

                    {/* Comments / activity */}
                    <div className="border-t pt-2 mt-1">
                      <div className="text-[11px] font-semibold text-gray-700 mb-1">Activity</div>
                      <div className="space-y-1 max-h-40 overflow-y-auto mb-2">
                        {selectedTask.comments.length === 0 ? (
                          <div className="text-[11px] text-gray-400">No comments yet.</div>
                        ) : (
                          selectedTask.comments.map((c) => (
                            <div key={c.id} className="text-[11px] text-gray-700">
                              <span className="font-semibold">
                                {c.author_name || (c.author_id ? c.author_id : 'System')}
                              </span>{' '}
                              <span className="text-gray-400">
                                {new Date(c.created_at).toLocaleString()}
                              </span>
                              <div
                                className={`ml-1 ${
                                  c.kind === 'status_change' || c.kind === 'snooze'
                                    ? 'text-gray-500 italic'
                                    : ''
                                }`}
                              >
                                {c.body}
                              </div>
                            </div>
                          ))
                        )}
                      </div>

                      <div className="flex flex-col gap-1">
                        <Textarea
                          rows={3}
                          className="text-xs"
                          placeholder="Add a comment..."
                          value={newComment}
                          onChange={(e) => setNewComment(e.target.value)}
                        />
                        <div className="flex justify-end">
                          <Button size="sm" variant="outline" disabled={!newComment.trim()} onClick={handleAddComment}>
                            Add comment
                          </Button>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Create modal */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New Task / Reminder</DialogTitle>
            <DialogDescription>Create a new task or reminder.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-gray-700">Type</span>
              <Button
                size="sm"
                variant={createPayload.type === 'task' ? 'default' : 'outline'}
                onClick={() => setCreatePayload((p) => ({ ...p, type: 'task' }))}
              >
                Task
              </Button>
              <Button
                size="sm"
                variant={createPayload.type === 'reminder' ? 'default' : 'outline'}
                onClick={() => setCreatePayload((p) => ({ ...p, type: 'reminder' }))}
              >
                Reminder
              </Button>
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Title</label>
              <Input
                className="h-8 text-xs"
                value={createPayload.title}
                onChange={(e) => setCreatePayload((p) => ({ ...p, title: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Description</label>
              <Textarea
                rows={3}
                className="text-xs"
                value={createPayload.description || ''}
                onChange={(e) => setCreatePayload((p) => ({ ...p, description: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[11px] font-semibold mb-1">Assignee ID</label>
                <Input
                  className="h-8 text-xs"
                  placeholder={createPayload.type === 'reminder' ? '(defaults to you)' : ''}
                  value={createPayload.assignee_id || ''}
                  onChange={(e) => setCreatePayload((p) => ({ ...p, assignee_id: e.target.value || undefined }))}
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1">
                  {createPayload.type === 'task' ? 'Due at' : 'Remind at'}
                </label>
                <Input
                  type="datetime-local"
                  className="h-8 text-xs"
                  value={createPayload.due_at || ''}
                  onChange={(e) => setCreatePayload((p) => ({ ...p, due_at: e.target.value || undefined }))}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 items-center">
              <div>
                <label className="block text-[11px] font-semibold mb-1">Priority</label>
                <select
                  className="border rounded px-2 py-1 text-xs w-full"
                  value={createPayload.priority || 'normal'}
                  onChange={(e) =>
                    setCreatePayload((p) => ({ ...p, priority: e.target.value as TaskCreatePayload['priority'] }))
                  }
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div className="flex items-center gap-2 mt-4">
                <input
                  id="show-popup"
                  type="checkbox"
                  className="h-3 w-3"
                  checked={createPayload.is_popup ?? true}
                  onChange={(e) => setCreatePayload((p) => ({ ...p, is_popup: e.target.checked }))}
                />
                <label htmlFor="show-popup" className="text-[11px] text-gray-700">
                  Show as popup
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!createPayload.title.trim() || creating}
              onClick={() => void handleCreateTask()}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default TasksPage;
