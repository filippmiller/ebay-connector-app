import React, { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import { Input } from './ui/input';
import { Download, Pause, Play, Trash2, Square } from 'lucide-react';
import api from '../lib/apiClient';

interface SyncEvent {
  run_id: string;
  event_type: string;
  level: string;
  message: string;
  http_method?: string;
  http_url?: string;
  http_status?: number;
  http_duration_ms?: number;
  current_page?: number;
  total_pages?: number;
  items_fetched?: number;
  items_stored?: number;
  progress_pct?: number;
  extra_data?: any;
  timestamp: string;
}

interface SyncTerminalProps {
  runId: string;
  onComplete?: (doneEvent?: any) => void;
  onStop?: () => void;
}

export const SyncTerminal: React.FC<SyncTerminalProps> = ({ runId, onComplete, onStop }) => {
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [isCancelled, setIsCancelled] = useState(false);
  const [visibleLimit, setVisibleLimit] = useState<number>(500);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const [search, setSearch] = useState('');

  // Load historical events on mount
  useEffect(() => {
    if (!runId) return;
    
    const loadHistoricalEvents = async () => {
      try {
        const response = await api.get(`/ebay/sync/logs/${runId}`);
        if (response.data?.events) {
          setEvents(response.data.events);
          // Check if already complete or cancelled - but only if we have a 'done' or 'cancelled' event
          const hasDoneEvent = response.data.events.some((e: SyncEvent) => e.event_type === 'done');
          const hasCancelledEvent = response.data.events.some((e: SyncEvent) => e.event_type === 'cancelled');
          
          if (hasDoneEvent) {
            setIsComplete(true);
          }
          if (hasCancelledEvent) {
            setIsCancelled(true);
            setIsComplete(true);
          }
        } else if (response.data?.events?.length === 0) {
          // No events yet - sync might not have started
          setEvents([{
            run_id: runId,
            event_type: 'log',
            level: 'info',
            message: 'Waiting for sync to start...',
            timestamp: new Date().toISOString()
          }]);
        }
      } catch (error: any) {
        console.error('Failed to load historical events:', error);
        // Show authentication error if applicable
        if (error?.response?.status === 401 || error?.response?.status === 403) {
          setEvents([{
            run_id: runId,
            event_type: 'error',
            level: 'error',
            message: 'Authentication error: Please log out and log back in to refresh your session.',
            timestamp: new Date().toISOString()
          }]);
        } else {
          setEvents([{
            run_id: runId,
            event_type: 'error',
            level: 'error',
            message: `Failed to load logs: ${error?.response?.data?.detail || error?.message || 'Unknown error'}`,
            timestamp: new Date().toISOString()
          }]);
        }
      }
    };
    
    loadHistoricalEvents();
  }, [runId]);

  useEffect(() => {
    if (!runId || isPaused || isComplete || isCancelled) return; // Don't reconnect if already complete/cancelled

    const token = localStorage.getItem('auth_token');
    const eventSource = new EventSource(`/api/ebay/sync/events/${runId}?token=${encodeURIComponent(token || '')}`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    // Helper function to check if event already exists (prevent duplicates)
    const eventExists = (events: any[], newEvent: any): boolean => {
      return events.some(e => 
        e.timestamp === newEvent.timestamp && 
        e.message === newEvent.message &&
        e.event_type === newEvent.event_type
      );
    };

    eventSource.addEventListener('start', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => {
        if (eventExists(prev, event)) return prev;
        return [...prev, event];
      });
    });

    eventSource.addEventListener('log', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => {
        if (eventExists(prev, event)) return prev;
        return [...prev, event];
      });
    });

    eventSource.addEventListener('http', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => {
        if (eventExists(prev, event)) return prev;
        return [...prev, event];
      });
    });

    eventSource.addEventListener('progress', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => {
        if (eventExists(prev, event)) return prev;
        return [...prev, event];
      });
    });

    eventSource.addEventListener('error', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => {
        if (eventExists(prev, event)) return prev;
        return [...prev, event];
      });
    });

    eventSource.addEventListener('done', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
      setIsComplete(true);
      setIsConnected(false);
      eventSource.close();
      // Call onComplete with the done event data so parent can extract counts
      if (onComplete) onComplete(event);
    });

    eventSource.addEventListener('cancelled', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
      setIsCancelled(true);
      setIsComplete(true);
      setIsConnected(false);
      eventSource.close();
      if (onComplete) onComplete();
    });

    eventSource.addEventListener('end', () => {
      setIsConnected(false);
      eventSource.close();
    });

    eventSource.onerror = (error) => {
      console.error('[SyncTerminal] EventSource error:', error);
      setIsConnected(false);
      eventSource.close();
      
      // Don't reconnect if already complete or cancelled
      if (isComplete || isCancelled) {
        return;
      }
      
      // Check if it's an authentication error by trying to load logs
      // If we get 401/403, show authentication error message
      const checkAuth = async () => {
        try {
          await api.get(`/ebay/sync/logs/${runId}`);
          // If we get here, auth is OK, so it's a different error
          // Only add error if not already complete
          if (!isComplete && !isCancelled) {
            setEvents((prev) => [...prev, {
              run_id: runId,
              event_type: 'error',
              level: 'error',
              message: 'Connection error: Failed to stream events. Check network connection.',
              timestamp: new Date().toISOString()
            }]);
          }
        } catch (err: any) {
          // Authentication error
          if (!isComplete && !isCancelled) {
            if (err?.response?.status === 401 || err?.response?.status === 403) {
              setEvents((prev) => [...prev, {
                run_id: runId,
                event_type: 'error',
                level: 'error',
                message: 'Authentication error: Please log out and log back in to refresh your session.',
                timestamp: new Date().toISOString()
              }]);
            } else {
              setEvents((prev) => [...prev, {
                run_id: runId,
                event_type: 'error',
                level: 'error',
                message: `Connection error: ${err?.response?.data?.detail || err?.message || 'Unknown error'}`,
                timestamp: new Date().toISOString()
              }]);
            }
          }
        }
      };
      checkAuth();
    };

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [runId, isPaused, isComplete, isCancelled]);

  useEffect(() => {
    if (scrollRef.current && !isPaused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, isPaused]);

  const handlePauseToggle = () => {
    setIsPaused(!isPaused);
    if (!isPaused && eventSourceRef.current) {
      eventSourceRef.current.close();
      setIsConnected(false);
    }
  };

  const handleClear = () => {
    setEvents([]);
  };

  const handleStop = async () => {
    try {
      await api.post(`/ebay/sync/cancel/${runId}`);
      setIsCancelled(true);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        setIsConnected(false);
      }
      if (onStop) onStop();
    } catch (error) {
      console.error('Failed to cancel sync:', error);
    }
  };

  const handleDownload = async () => {
    try {
      const response = await fetch(`/api/ebay/sync/logs/${runId}/export`);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sync_logs_${runId}.ndjson`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Failed to download logs:', error);
    }
  };

  const getEventColor = (event: SyncEvent) => {
    if (event.level === 'error') return 'text-red-400';
    if (event.level === 'warning') return 'text-yellow-400';
    if (event.level === 'debug') return 'text-purple-400';
    if (event.event_type === 'start') return 'text-green-400';
    if (event.event_type === 'done') return 'text-green-400 font-bold';
    if (event.event_type === 'http') return 'text-blue-400';
    if (event.event_type === 'progress') return 'text-cyan-400';
    return 'text-gray-300';
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const formatEvent = (event: SyncEvent) => {
    const time = formatTimestamp(event.timestamp);
    let message = event.message;

    if (event.event_type === 'progress' && event.progress_pct !== undefined) {
      const progressBar = '█'.repeat(Math.floor(event.progress_pct / 5)) + '░'.repeat(20 - Math.floor(event.progress_pct / 5));
      message += ` [${progressBar}] ${event.progress_pct.toFixed(1)}%`;
    }

    // For debug messages, preserve multi-line format
    if (event.level === 'debug' && message.includes('\n')) {
      return `[${time}] ${message}`;
    }

    return `[${time}] ${message}`;
  };

  // Apply search & limit
  const filteredEvents = events.filter((event) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    try {
      return (
        (event.message || '').toLowerCase().includes(q) ||
        (event.http_url || '').toLowerCase().includes(q) ||
        (event.event_type || '').toLowerCase().includes(q)
      );
    } catch {
      return false;
    }
  });
  const limitedEvents = filteredEvents.slice(Math.max(filteredEvents.length - visibleLimit, 0));

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <span className="font-mono text-sm">Terminal</span>
            {isConnected && (
              <span className="flex items-center gap-1 text-xs text-green-500">
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                Live
              </span>
            )}
            {isComplete && !isCancelled && (
              <span className="text-xs text-gray-500">
                Complete
              </span>
            )}
            {isCancelled && (
              <span className="text-xs text-red-500">
                Cancelled
              </span>
            )}
          </CardTitle>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span>Show</span>
              <select
                value={visibleLimit}
                onChange={(e) => setVisibleLimit(Number(e.target.value) || 500)}
                className="h-8 rounded border border-gray-700 bg-gray-900 text-gray-100 text-xs px-2"
              >
                <option value={200}>200</option>
                <option value={500}>500</option>
                <option value={2000}>2000</option>
                <option value={5000}>5000</option>
              </select>
              <span>events</span>
            </div>
            <Input
              placeholder="Search events"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 w-44 text-xs bg-gray-900 text-gray-100 border-gray-700"
            />
            {(!isComplete || isConnected) && !isCancelled && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleStop}
                title="Stop sync"
                className="text-red-500 hover:text-red-700 hover:bg-red-50"
                disabled={isComplete && !isConnected}
              >
                <Square className="w-4 h-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePauseToggle}
              title={isPaused ? 'Resume' : 'Pause'}
              disabled={isComplete || isCancelled}
            >
              {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              title="Clear"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDownload}
              title="Download logs"
              disabled={!isComplete && !isCancelled}
            >
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="min-h-[50vh] max-h-[70vh] w-full rounded-md border bg-gray-950 p-4 font-mono text-sm overflow-auto" ref={scrollRef}>
          {limitedEvents.length === 0 ? (
            <div className="text-gray-500">Waiting for sync to start...</div>
          ) : (
            <div className="space-y-1">
              {limitedEvents.map((event, index) => (
                <div 
                  key={index} 
                  className={`${getEventColor(event)} ${event.level === 'debug' && event.message.includes('\n') ? 'whitespace-pre' : ''}`}
                >
                  {formatEvent(event)}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
};
