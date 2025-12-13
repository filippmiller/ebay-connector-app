/**
 * SessionTimeline Component
 * 
 * Displays the conversation history between brain and operator
 * as a visual timeline.
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { ScrollArea } from '../ui/scroll-area';
import {
  Brain,
  User,
  Check,
  X,
  MessageSquare,
  Play,
  Pause,
  Square,
  Clock,
  Zap,
} from 'lucide-react';
import type { HistoryEntry } from '../../api/brain';

interface SessionTimelineProps {
  history: HistoryEntry[];
  className?: string;
}

const getIcon = (role: string, type: string) => {
  if (role === 'brain') {
    return <Brain className="h-4 w-4 text-purple-400" />;
  }
  if (role === 'operator') {
    if (type === 'action_confirmed') return <Check className="h-4 w-4 text-green-400" />;
    if (type === 'action_rejected') return <X className="h-4 w-4 text-red-400" />;
    return <User className="h-4 w-4 text-cyan-400" />;
  }
  if (role === 'system') {
    if (type === 'session_started') return <Play className="h-4 w-4 text-green-400" />;
    if (type === 'session_paused') return <Pause className="h-4 w-4 text-yellow-400" />;
    if (type === 'session_ended') return <Square className="h-4 w-4 text-red-400" />;
    return <Zap className="h-4 w-4 text-cyan-400" />;
  }
  return <MessageSquare className="h-4 w-4 text-slate-400" />;
};

const getRoleBadge = (role: string) => {
  switch (role) {
    case 'brain':
      return <Badge className="bg-purple-600 text-xs">Мозг</Badge>;
    case 'operator':
      return <Badge className="bg-cyan-600 text-xs">Оператор</Badge>;
    case 'system':
      return <Badge variant="secondary" className="text-xs">Система</Badge>;
    default:
      return <Badge variant="outline" className="text-xs">{role}</Badge>;
  }
};

const formatTime = (timestamp: string) => {
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '';
  }
};

export const SessionTimeline: React.FC<SessionTimelineProps> = ({
  history,
  className = '',
}) => {
  return (
    <Card className={`${className} bg-slate-900/50 border-slate-700`}>
      <CardHeader className="pb-2">
        <CardTitle className="text-white flex items-center gap-2 text-lg">
          <Clock className="h-5 w-5 text-cyan-400" />
          История сессии
        </CardTitle>
      </CardHeader>
      
      <CardContent className="p-0">
        <ScrollArea className="h-[400px]">
          {history.length === 0 ? (
            <div className="p-6 text-center text-slate-500">
              История пуста. Запустите сессию.
            </div>
          ) : (
            <div className="p-4 space-y-3">
              {history.map((entry, i) => (
                <div
                  key={i}
                  className={`relative pl-6 pb-3 ${
                    i < history.length - 1 ? 'border-l border-slate-700' : ''
                  }`}
                >
                  {/* Timeline dot */}
                  <div className="absolute left-0 -translate-x-1/2 w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center">
                    {getIcon(entry.role, entry.type)}
                  </div>
                  
                  {/* Content */}
                  <div className="ml-4">
                    <div className="flex items-center gap-2 mb-1">
                      {getRoleBadge(entry.role)}
                      <span className="text-xs text-slate-500">
                        {formatTime(entry.timestamp)}
                      </span>
                    </div>
                    <p className="text-sm text-slate-300">{entry.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
};

export default SessionTimeline;

