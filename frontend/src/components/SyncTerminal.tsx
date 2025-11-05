import React, { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import { Download, Pause, Play, Trash2 } from 'lucide-react';

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
  onComplete?: () => void;
}

export const SyncTerminal: React.FC<SyncTerminalProps> = ({ runId, onComplete }) => {
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId || isPaused) return;

    const token = localStorage.getItem('auth_token');
    const eventSource = new EventSource(`/api/ebay/sync/events/${runId}?token=${encodeURIComponent(token || '')}`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    eventSource.addEventListener('start', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    });

    eventSource.addEventListener('log', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    });

    eventSource.addEventListener('http', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    });

    eventSource.addEventListener('progress', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    });

    eventSource.addEventListener('error', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    });

    eventSource.addEventListener('done', (e: MessageEvent) => {
      const event = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
      setIsComplete(true);
      setIsConnected(false);
      eventSource.close();
      if (onComplete) onComplete();
    });

    eventSource.addEventListener('end', () => {
      setIsConnected(false);
      eventSource.close();
    });

    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [runId, isPaused, onComplete]);

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

    return `[${time}] ${message}`;
  };

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
            {isComplete && (
              <span className="text-xs text-gray-500">
                Complete
              </span>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePauseToggle}
              title={isPaused ? 'Resume' : 'Pause'}
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
              disabled={!isComplete}
            >
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[600px] w-full rounded-md border bg-gray-950 p-4 font-mono text-sm" ref={scrollRef}>
          {events.length === 0 ? (
            <div className="text-gray-500">Waiting for sync to start...</div>
          ) : (
            <div className="space-y-1">
              {events.map((event, index) => (
                <div key={index} className={getEventColor(event)}>
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
