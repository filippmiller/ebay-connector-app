/**
 * DebugConsole Component
 * 
 * Real-time log viewer for CV module with WebSocket streaming
 * Shows logs from all subsystems with filtering and search
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { ScrollArea } from '../ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { 
  Terminal, 
  Trash2, 
  Download, 
  Pause, 
  Play,
  Filter,
  Search,
  Wifi,
  WifiOff
} from 'lucide-react';
import { getLogsWebSocketUrl, LogEntry } from '../../api/cv';

interface DebugConsoleProps {
  autoConnect?: boolean;
  maxLogs?: number;
  className?: string;
}

const SUBSYSTEM_COLORS: Record<string, string> = {
  CAMERA: 'bg-blue-500',
  STREAM: 'bg-cyan-500',
  CV: 'bg-purple-500',
  OCR: 'bg-yellow-500',
  SUPABASE: 'bg-green-500',
  ERROR: 'bg-red-500',
  SYSTEM: 'bg-gray-500',
};

const LEVEL_COLORS: Record<string, string> = {
  debug: 'text-gray-400',
  info: 'text-blue-400',
  warn: 'text-yellow-400',
  error: 'text-red-400',
  critical: 'text-red-600 font-bold',
};

export const DebugConsole: React.FC<DebugConsoleProps> = ({
  autoConnect = true,
  maxLogs = 500,
  className = '',
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);

  const addLog = useCallback((entry: LogEntry) => {
    if (paused) return;
    
    setLogs(prev => {
      const newLogs = [...prev, entry];
      // Keep only the last maxLogs entries
      if (newLogs.length > maxLogs) {
        return newLogs.slice(-maxLogs);
      }
      return newLogs;
    });
  }, [paused, maxLogs]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = getLogsWebSocketUrl();
    const ws = new WebSocket(url);
    
    ws.onopen = () => {
      setConnected(true);
      console.log('[DebugConsole] Connected to log stream');
    };
    
    ws.onclose = () => {
      setConnected(false);
      console.log('[DebugConsole] Disconnected from log stream');
    };
    
    ws.onerror = (error) => {
      console.error('[DebugConsole] WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'history' && Array.isArray(data.logs)) {
          setLogs(data.logs);
        } else if (data.timestamp && data.message) {
          addLog(data);
        }
      } catch (e) {
        console.error('[DebugConsole] Failed to parse message:', e);
      }
    };
    
    wsRef.current = ws;
  }, [addLog]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const clearLogs = () => {
    setLogs([]);
  };

  const downloadLogs = () => {
    const content = logs
      .map(log => `[${log.timestamp}] [${log.level.toUpperCase()}] [${log.subsystem}] ${log.message}`)
      .join('\n');
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cv-logs-${new Date().toISOString()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredLogs = logs.filter(log => {
    if (filter !== 'all' && log.subsystem !== filter) return false;
    if (levelFilter !== 'all' && log.level !== levelFilter) return false;
    if (searchTerm && !log.message.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLogs, autoScroll]);

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', { 
        hour12: false, 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit',
        fractionalSecondDigits: 3
      });
    } catch {
      return timestamp;
    }
  };

  return (
    <Card className={`flex flex-col ${className}`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Terminal className="h-5 w-5" />
            Debug Console
          </CardTitle>
          <div className="flex items-center gap-2">
            {connected ? (
              <Badge variant="default" className="bg-green-600">
                <Wifi className="h-3 w-3 mr-1" />
                Live
              </Badge>
            ) : (
              <Badge variant="secondary">
                <WifiOff className="h-3 w-3 mr-1" />
                Offline
              </Badge>
            )}
            <Badge variant="outline">{filteredLogs.length} logs</Badge>
          </div>
        </div>
        
        {/* Filters */}
        <div className="flex items-center gap-2 mt-2">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Search logs..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-8 h-9"
            />
          </div>
          
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-32 h-9">
              <Filter className="h-4 w-4 mr-1" />
              <SelectValue placeholder="Subsystem" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="CAMERA">Camera</SelectItem>
              <SelectItem value="STREAM">Stream</SelectItem>
              <SelectItem value="CV">CV</SelectItem>
              <SelectItem value="OCR">OCR</SelectItem>
              <SelectItem value="SUPABASE">Supabase</SelectItem>
              <SelectItem value="SYSTEM">System</SelectItem>
              <SelectItem value="ERROR">Error</SelectItem>
            </SelectContent>
          </Select>
          
          <Select value={levelFilter} onValueChange={setLevelFilter}>
            <SelectTrigger className="w-28 h-9">
              <SelectValue placeholder="Level" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="debug">Debug</SelectItem>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warn">Warn</SelectItem>
              <SelectItem value="error">Error</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      
      <CardContent className="flex-1 p-0 flex flex-col min-h-0">
        {/* Log Output */}
        <ScrollArea 
          ref={scrollRef}
          className="flex-1 bg-gray-950 font-mono text-xs"
        >
          <div className="p-2 space-y-0.5">
            {filteredLogs.length === 0 ? (
              <div className="text-gray-500 text-center py-8">
                {connected ? 'No logs yet...' : 'Connect to see logs'}
              </div>
            ) : (
              filteredLogs.map((log, i) => (
                <div key={i} className="flex items-start gap-2 py-0.5 hover:bg-gray-900/50">
                  <span className="text-gray-500 shrink-0">
                    {formatTimestamp(log.timestamp)}
                  </span>
                  <Badge 
                    variant="secondary" 
                    className={`${SUBSYSTEM_COLORS[log.subsystem] || 'bg-gray-500'} text-white text-[10px] px-1.5 py-0 shrink-0`}
                  >
                    {log.subsystem}
                  </Badge>
                  <span className={LEVEL_COLORS[log.level] || 'text-white'}>
                    {log.message}
                  </span>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
        
        {/* Controls */}
        <div className="p-2 bg-gray-900 border-t border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {!connected ? (
              <Button size="sm" variant="secondary" onClick={connect}>
                <Wifi className="h-4 w-4 mr-1" />
                Connect
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={disconnect}>
                <WifiOff className="h-4 w-4 mr-1" />
                Disconnect
              </Button>
            )}
            
            <Button
              size="sm"
              variant={paused ? 'default' : 'outline'}
              onClick={() => setPaused(!paused)}
            >
              {paused ? (
                <>
                  <Play className="h-4 w-4 mr-1" />
                  Resume
                </>
              ) : (
                <>
                  <Pause className="h-4 w-4 mr-1" />
                  Pause
                </>
              )}
            </Button>
          </div>
          
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={downloadLogs}>
              <Download className="h-4 w-4" />
            </Button>
            <Button size="sm" variant="outline" onClick={clearLogs}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default DebugConsole;

