import React, { useEffect, useMemo, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { ScrollArea } from './ui/scroll-area';
import { Button } from './ui/button';
import type {
  WorkerDebugTrace,
  WorkerDebugStep,
  WorkerDebugDbChange,
  WorkerDebugHttp,
} from '@/api/ebayListingWorker';

export interface WorkerDebugTerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  trace: WorkerDebugTrace | null;
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString(undefined, {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return ts;
  }
}

function renderDbChange(change: WorkerDebugDbChange) {
  const entries = Object.entries(change.changes || {});
  if (!entries.length) return null;
  return (
    <div className="ml-4 text-[11px] text-gray-300">
      {entries.map(([col, diff]) => (
        <div key={col} className="whitespace-pre-wrap break-all">
          <span className="text-blue-200">{col}</span>:
          {' '}
          <span className="text-gray-400">{JSON.stringify(diff.old)}</span>
          {' '}
          <span className="text-gray-500">→</span>
          {' '}
          <span className="text-green-300">{JSON.stringify(diff.new)}</span>
        </div>
      ))}
    </div>
  );
}

function renderHttp(http: WorkerDebugHttp, kind: 'request' | 'response') {
  return (
    <div className="ml-4 text-[11px] text-gray-300">
      <div className="mb-1">
        <span className="text-blue-200">{http.method}</span>
        {' '}
        <span className="text-gray-200">{http.url}</span>
        {kind === 'response' && http.status_code != null && (
          <span className="ml-2 text-yellow-200">[{http.status_code}]</span>
        )}
        {http.duration_ms != null && (
          <span className="ml-2 text-gray-400">{http.duration_ms} ms</span>
        )}
      </div>
      {http.headers && Object.keys(http.headers).length > 0 && (
        <div className="mb-1">
          <span className="text-gray-400">headers:</span>
          <pre className="mt-0.5 whitespace-pre-wrap break-all text-[10px] text-gray-400 bg-black/20 px-2 py-1 rounded">
            {JSON.stringify(http.headers, null, 2)}
          </pre>
        </div>
      )}
      {http.body !== undefined && http.body !== null && (
        <div className="mb-1">
          <span className="text-gray-400">body:</span>
          <pre className="mt-0.5 whitespace-pre-wrap break-all text-[10px] text-gray-400 bg-black/20 px-2 py-1 rounded">
            {JSON.stringify(http.body, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function stepColor(type: WorkerDebugStep['type']): string {
  switch (type) {
    case 'error':
      return 'text-red-300';
    case 'db-update':
    case 'log-insert':
      return 'text-green-300';
    case 'ebay-request':
    case 'ebay-response':
      return 'text-blue-300';
    default:
      return 'text-gray-200';
  }
}

export const WorkerDebugTerminalModal: React.FC<WorkerDebugTerminalModalProps> = ({
  isOpen,
  onClose,
  trace,
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const steps = trace?.steps ?? [];

  const startEnd = useMemo(() => {
    if (!steps.length) return { start: null as string | null, end: null as string | null };
    return { start: steps[0].timestamp, end: steps[steps.length - 1].timestamp };
  }, [steps]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps.length, isOpen]);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl h-[70vh] flex flex-col bg-black text-gray-100">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between text-sm font-mono">
            <span>
              eBay Listing Worker Debug
              {trace && (
                <span className="ml-2 text-xs text-gray-400">
                  job_id={trace.job_id}
                </span>
              )}
            </span>
            <span className="text-xs text-gray-400 flex items-center gap-3">
              {trace?.account && <span>account={trace.account}</span>}
              {typeof trace?.items_count === 'number' && (
                <span>items={trace.items_count}</span>
              )}
              {startEnd.start && (
                <span>
                  window=
                  {formatTime(startEnd.start)}
                  {' → '}
                  {startEnd.end ? formatTime(startEnd.end) : '—'}
                </span>
              )}
            </span>
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 flex flex-col border border-gray-700 bg-black/80 rounded-md overflow-hidden">
          <div
            ref={scrollRef}
            className="flex-1 overflow-auto font-mono text-[11px] leading-snug p-2"
          >
            <ScrollArea className="h-full w-full">
              <div className="space-y-1">
                {steps.map((step, idx) => {
                  const time = formatTime(step.timestamp);
                  return (
                    <div key={idx} className="whitespace-pre-wrap break-all">
                      <span className="text-gray-500 mr-2">[{time}]</span>
                      <span className={`mr-2 ${stepColor(step.type)}`}>[{step.type}]</span>
                      {step.label && (
                        <span className="text-purple-300 mr-1">{step.label}</span>
                      )}
                      <span>{step.message}</span>
                      {step.http && (
                        <div className="mt-1">
                          {renderHttp(step.http, step.type === 'ebay-response' ? 'response' : 'request')}
                        </div>
                      )}
                      {step.db_change && (
                        <div className="mt-1">
                          <div className="ml-4 text-[11px] text-gray-300 mb-0.5">
                            table=
                            {step.db_change.table_name} row_id=
                            {step.db_change.row_id}
                          </div>
                          {renderDbChange(step.db_change)}
                        </div>
                      )}
                    </div>
                  );
                })}
                {!steps.length && (
                  <div className="text-gray-400">No debug steps recorded.</div>
                )}
              </div>
            </ScrollArea>
          </div>
          <div className="border-t border-gray-700 px-2 py-1 flex items-center justify-between bg-black/70 text-xs">
            <span className="text-gray-500">
              Debug mode only. Sensitive headers and tokens are masked in this view.
            </span>
            <Button size="sm" variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
