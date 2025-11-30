import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Check, Clock, MessageCircle, Play, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  TaskNotificationItem,
  getUnreadTaskNotifications,
  markTaskNotificationRead,
  dismissTaskNotification,
  changeTaskStatus,
  snoozeTask,
} from '@/api/tasks';

interface ToastItem extends TaskNotificationItem {
  // Local-only fields for UI state
  _localId: string;
}

const MAX_VISIBLE_TOASTS = 3;
const POLL_INTERVAL_MS = 20000;

const getNotificationLabel = (n: TaskNotificationItem): string => {
  const title = n.task?.title || 'Untitled';
  switch (n.kind) {
    case 'task_assigned':
      return `New task: ${title}`;
    case 'task_status_changed':
      return `Status changed: ${title}`;
    case 'task_comment_added':
      return `New comment on: ${title}`;
    case 'reminder_fired':
      return `Reminder: ${title}`;
    case 'ebay_watch_match':
      return `eBay match: ${title}`;
    default:
      return title;
  }
};

const getNotificationSubtitle = (n: TaskNotificationItem): string => {
  if (n.kind === 'task_assigned') {
    const from = n.task?.creator_username || 'Someone';
    return `Assigned by ${from}`;
  }
  if (n.kind === 'task_status_changed') {
    return `Status: ${n.task?.status || 'updated'}`;
  }
  if (n.kind === 'task_comment_added') {
    return 'New comment added';
  }
  if (n.kind === 'reminder_fired') {
    return 'Reminder is due';
  }
  if (n.kind === 'ebay_watch_match') {
    return 'Новый лот, найденный авто-поиском eBay';
  }
  return '';
};

const isReminder = (n: TaskNotificationItem) => n.task?.type === 'reminder';

export const TaskNotificationsBell: React.FC = () => {
  const navigate = useNavigate();

  const [notifications, setNotifications] = useState<TaskNotificationItem[]>([]);
  const [badgeCount, setBadgeCount] = useState(0);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const [visibleToasts, setVisibleToasts] = useState<ToastItem[]>([]);
  const toastQueueRef = useRef<ToastItem[]>([]);
  const seenIdsRef = useRef<Set<string>>(new Set());
  const hasInitialLoadRef = useRef(false);

  const [lastSince, setLastSince] = useState<string | undefined>(undefined);

  const enqueueToasts = useCallback((items: TaskNotificationItem[]) => {
    if (!items.length) return;
    const newToasts: ToastItem[] = items.map((n) => ({ ...n, _localId: `${n.id}-${Date.now()}-${Math.random()}` }));
    toastQueueRef.current = [...toastQueueRef.current, ...newToasts];
    setVisibleToasts((current) => {
      const freeSlots = MAX_VISIBLE_TOASTS - current.length;
      if (freeSlots <= 0) return current;
      const next = toastQueueRef.current.slice(0, freeSlots);
      toastQueueRef.current = toastQueueRef.current.slice(freeSlots);
      return [...current, ...next];
    });
  }, []);

  const loadNotifications = useCallback(async () => {
    try {
      const resp = await getUnreadTaskNotifications();
      const items = Array.isArray(resp.items) ? resp.items : [];
      setNotifications(items);
      setBadgeCount(items.length);

      // Track new items for toasts
      const sorted = [...items].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
      const latestCreated = sorted[0]?.created_at;
      if (latestCreated) {
        setLastSince(latestCreated);
      }

      if (!hasInitialLoadRef.current) {
        // On first load, don't spam user with historical notifications
        items.forEach((n) => seenIdsRef.current.add(n.id));
        hasInitialLoadRef.current = true;
        return;
      }

      const fresh = items.filter((n) => !seenIdsRef.current.has(n.id));
      if (fresh.length) {
        fresh.forEach((n) => seenIdsRef.current.add(n.id));
        enqueueToasts(fresh);
      }
    } catch (e) {
      console.error('Failed to load task notifications', e);
    }
  }, [enqueueToasts]);

  useEffect(() => {
    void loadNotifications();
    const id = window.setInterval(() => {
      void loadNotifications();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [loadNotifications]);

  const handleOpenTask = useCallback(
    async (n: TaskNotificationItem) => {
      try {
        await markTaskNotificationRead(n.id);
      } catch (e) {
        console.error('Failed to mark notification as read', e);
      }
      setNotifications((prev) => prev.filter((x) => x.id !== n.id));
      setBadgeCount((prev) => Math.max(0, prev - 1));
      navigate(`/tasks?taskId=${encodeURIComponent(n.task_id)}`);
    },
    [navigate],
  );

  const handleQuickStatusChange = useCallback(
    async (n: TaskNotificationItem, newStatus: string) => {
      try {
        await changeTaskStatus(n.task_id, { new_status: newStatus });
        await markTaskNotificationRead(n.id);
        setNotifications((prev) => prev.filter((x) => x.id !== n.id));
        setBadgeCount((prev) => Math.max(0, prev - 1));
      } catch (e) {
        console.error('Failed to change task status from notification', e);
      }
    },
    [],
  );

  const handleSnoozeQuick = useCallback(
    async (n: TaskNotificationItem, preset: '15m' | '1h' | 'tomorrow') => {
      try {
        await snoozeTask(n.task_id, { preset });
        await dismissTaskNotification(n.id);
        setNotifications((prev) => prev.filter((x) => x.id !== n.id));
        setBadgeCount((prev) => Math.max(0, prev - 1));
      } catch (e) {
        console.error('Failed to snooze reminder from notification', e);
      }
    },
    [],
  );

  const handleDismissNotification = useCallback(async (n: TaskNotificationItem) => {
    try {
      await dismissTaskNotification(n.id);
    } catch (e) {
      console.error('Failed to dismiss notification', e);
    }
    setNotifications((prev) => prev.filter((x) => x.id !== n.id));
    setBadgeCount((prev) => Math.max(0, prev - 1));
  }, []);

  const handleToastClose = useCallback(
    async (toast: ToastItem, markDismiss: boolean = true) => {
      if (markDismiss) {
        try {
          await dismissTaskNotification(toast.id);
        } catch (e) {
          console.error('Failed to dismiss toast notification', e);
        }
      }

      setVisibleToasts((prev) => prev.filter((t) => t._localId !== toast._localId));
      setTimeout(() => {
        setVisibleToasts((prev) => {
          if (prev.length >= MAX_VISIBLE_TOASTS) return prev;
          const queue = toastQueueRef.current;
          if (!queue.length) return prev;
          const next = queue[0];
          toastQueueRef.current = queue.slice(1);
          return [...prev, next];
        });
      }, 0);
    },
    [],
  );

  const sortedNotifications = useMemo(
    () => [...notifications].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [notifications],
  );

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="relative h-8 w-8"
        onClick={() => setDropdownOpen((open) => !open)}
      >
        <Bell className="h-4 w-4" />
        {badgeCount > 0 && (
          <span className="absolute -top-1 -right-1 inline-flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] px-1.5 py-0.5 min-w-[18px]">
            {badgeCount > 99 ? '99+' : badgeCount}
          </span>
        )}
        <span className="sr-only">Tasks & reminders notifications</span>
      </Button>

      {dropdownOpen && (
        <div className="absolute right-0 mt-2 w-96 max-h-[24rem] overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg z-50">
          <div className="px-3 py-2 border-b flex items-center justify-between">
            <span className="text-xs font-semibold tracking-wide text-gray-600">
              Tasks & Reminders
            </span>
            {lastSince && (
              <span className="text-[10px] text-gray-400">Updated {new Date(lastSince).toLocaleTimeString()}</span>
            )}
          </div>

          {sortedNotifications.length === 0 ? (
            <div className="px-4 py-6 text-xs text-gray-500 text-center">No unread notifications</div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {sortedNotifications.map((n) => (
                <li
                  key={n.id}
                  className="px-3 py-2.5 text-xs hover:bg-gray-50 cursor-pointer flex flex-col gap-1"
                  onClick={() => handleOpenTask(n)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${
                          isReminder(n)
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-blue-100 text-blue-700'
                        }`}
                      >
                        {isReminder(n) ? <Clock className="h-3 w-3" /> : <Check className="h-3 w-3" />}
                      </span>
                      <div className="flex flex-col">
                        <span className="font-semibold text-gray-800 truncate max-w-[14rem]">
                          {getNotificationLabel(n)}
                        </span>
                        {getNotificationSubtitle(n) && (
                          <span className="text-[11px] text-gray-500 truncate max-w-[14rem]">
                            {getNotificationSubtitle(n)}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-[10px] text-gray-400 whitespace-nowrap">
                      {new Date(n.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="flex items-center justify-end gap-1 mt-1">
                    {!isReminder(n) && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleQuickStatusChange(n, 'in_progress');
                          }}
                        >
                          <Play className="h-3 w-3 mr-1" /> Start
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleQuickStatusChange(n, 'done');
                          }}
                        >
                          <Check className="h-3 w-3 mr-1" /> Done
                        </Button>
                      </>
                    )}
                    {isReminder(n) && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleQuickStatusChange(n, 'done');
                          }}
                        >
                          <Check className="h-3 w-3 mr-1" /> Done
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleSnoozeQuick(n, '15m');
                          }}
                        >
                          <Clock className="h-3 w-3 mr-1" /> 15m
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleSnoozeQuick(n, '1h');
                          }}
                        >
                          <Clock className="h-3 w-3 mr-1" /> 1h
                        </Button>
                      </>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDismissNotification(n);
                      }}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Corner popups */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {visibleToasts.map((toast) => (
          <div
            key={toast._localId}
            className="bg-white border border-gray-200 shadow-lg rounded-md p-3 text-xs flex flex-col gap-2 max-w-sm"
          >
            <div className="flex items-start gap-2">
              <span
                className={`mt-0.5 inline-flex h-6 w-6 items-center justify-center rounded-full ${
                  isReminder(toast)
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-blue-100 text-blue-700'
                }`}
              >
                {isReminder(toast) ? <Clock className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />}
              </span>
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-gray-800 truncate">
                    {getNotificationLabel(toast)}
                  </div>
                  <button
                    className="text-gray-400 hover:text-gray-600"
                    onClick={() => void handleToastClose(toast)}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
                {getNotificationSubtitle(toast) && (
                  <div className="text-[11px] text-gray-500 mt-0.5">
                    {getNotificationSubtitle(toast)}
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center justify-end gap-1 mt-1">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  void handleOpenTask(toast);
                  void handleToastClose(toast, false);
                }}
              >
                <MessageCircle className="h-3 w-3 mr-1" /> Open
              </Button>
              {!isReminder(toast) && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleQuickStatusChange(toast, 'in_progress');
                      void handleToastClose(toast, false);
                    }}
                  >
                    <Play className="h-3 w-3 mr-1" /> Start
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleQuickStatusChange(toast, 'done');
                      void handleToastClose(toast, false);
                    }}
                  >
                    <Check className="h-3 w-3 mr-1" /> Done
                  </Button>
                </>
              )}
              {isReminder(toast) && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleQuickStatusChange(toast, 'done');
                      void handleToastClose(toast, false);
                    }}
                  >
                    <Check className="h-3 w-3 mr-1" /> Done
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleSnoozeQuick(toast, '15m');
                      void handleToastClose(toast, false);
                    }}
                  >
                    <Clock className="h-3 w-3 mr-1" /> 15m
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleSnoozeQuick(toast, '1h');
                      void handleToastClose(toast, false);
                    }}
                  >
                    <Clock className="h-3 w-3 mr-1" /> 1h
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleSnoozeQuick(toast, 'tomorrow');
                      void handleToastClose(toast, false);
                    }}
                  >
                    <Clock className="h-3 w-3 mr-1" /> Tomorrow
                  </Button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TaskNotificationsBell;
