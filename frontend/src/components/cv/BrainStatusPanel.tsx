/**
 * BrainStatusPanel Component
 * 
 * Displays real-time status of the vision brain system
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import {
  Brain,
  Eye,
  FileText,
  Activity,
  Users,
  Zap,
} from 'lucide-react';
import type { BrainStatus, SessionState } from '../../api/brain';

interface BrainStatusPanelProps {
  status: BrainStatus | null;
  sessionState: SessionState | null;
  className?: string;
}

const getStateColor = (state: string) => {
  switch (state) {
    case 'scanning':
    case 'active':
      return 'bg-green-500';
    case 'analyzing':
      return 'bg-blue-500';
    case 'waiting_for_operator':
      return 'bg-yellow-500';
    case 'completed':
      return 'bg-cyan-500';
    case 'error':
      return 'bg-red-500';
    default:
      return 'bg-slate-500';
  }
};

const getStateLabel = (state: string) => {
  switch (state) {
    case 'idle':
      return 'Ожидание';
    case 'scanning':
      return 'Сканирование';
    case 'analyzing':
      return 'Анализ';
    case 'waiting_for_operator':
      return 'Ожидание оператора';
    case 'processing_response':
      return 'Обработка ответа';
    case 'completed':
      return 'Завершено';
    case 'error':
      return 'Ошибка';
    default:
      return state;
  }
};

export const BrainStatusPanel: React.FC<BrainStatusPanelProps> = ({
  status,
  sessionState,
  className = '',
}) => {
  const state = sessionState?.session_state || 'idle';
  const stats = status?.stats || {
    total_frames: 0,
    total_detections: 0,
    total_ocr_results: 0,
    total_brain_calls: 0,
    total_operator_events: 0,
  };

  return (
    <Card className={`${className} bg-slate-900/50 border-slate-700`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-white flex items-center gap-2">
            <Brain className="h-5 w-5 text-purple-400" />
            Статус мозга
          </CardTitle>
          <Badge className={getStateColor(state)}>
            {getStateLabel(state)}
          </Badge>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Brain Status */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-slate-800 rounded-lg">
            <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
              <Brain className="h-4 w-4" />
              Мозг
            </div>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${
                status?.brain_initialized ? 'bg-green-500' : 'bg-red-500'
              }`} />
              <span className="text-white text-sm">
                {status?.brain_initialized ? 'Готов' : 'Не инициализирован'}
              </span>
            </div>
          </div>
          
          <div className="p-3 bg-slate-800 rounded-lg">
            <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
              <Zap className="h-4 w-4" />
              Режим
            </div>
            <span className="text-white text-sm capitalize">
              {status?.brain_mode?.replace('_', ' ') || 'N/A'}
            </span>
          </div>
        </div>
        
        {/* Session Stats */}
        {sessionState?.session_id && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-slate-400">Статистика сессии</h4>
            
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="flex items-center justify-between p-2 bg-slate-800 rounded">
                <span className="text-slate-400 flex items-center gap-1">
                  <Activity className="h-3 w-3" />
                  Кадры
                </span>
                <span className="text-white font-mono">
                  {sessionState.frame_counter.toLocaleString()}
                </span>
              </div>
              
              <div className="flex items-center justify-between p-2 bg-slate-800 rounded">
                <span className="text-slate-400 flex items-center gap-1">
                  <Eye className="h-3 w-3" />
                  Детекции
                </span>
                <span className="text-white font-mono">
                  {sessionState.detection_counter.toLocaleString()}
                </span>
              </div>
              
              <div className="flex items-center justify-between p-2 bg-slate-800 rounded">
                <span className="text-slate-400 flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  OCR
                </span>
                <span className="text-white font-mono">
                  {sessionState.ocr_counter.toLocaleString()}
                </span>
              </div>
              
              <div className="flex items-center justify-between p-2 bg-slate-800 rounded">
                <span className="text-slate-400 flex items-center gap-1">
                  <Brain className="h-3 w-3" />
                  Решения
                </span>
                <span className="text-white font-mono">
                  {stats.total_brain_calls}
                </span>
              </div>
            </div>
          </div>
        )}
        
        {/* Connected Operators */}
        <div className="flex items-center justify-between p-3 bg-slate-800 rounded-lg">
          <div className="flex items-center gap-2 text-slate-400">
            <Users className="h-4 w-4" />
            <span className="text-sm">Операторы онлайн</span>
          </div>
          <Badge variant={status?.connected_operators ? 'default' : 'secondary'}>
            {status?.connected_operators || 0}
          </Badge>
        </div>
        
        {/* Latest Decision Preview */}
        {sessionState?.latest_decision && (
          <div className="p-3 bg-purple-900/20 rounded-lg border border-purple-700/50">
            <div className="flex items-center gap-2 text-purple-400 text-sm mb-2">
              <Brain className="h-4 w-4" />
              Последнее решение
            </div>
            <div className="flex items-center justify-between">
              <Badge variant="outline" className="text-xs">
                {sessionState.latest_decision.decision_type}
              </Badge>
              <span className="text-sm text-slate-400">
                {(sessionState.latest_decision.confidence * 100).toFixed(0)}% уверенность
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default BrainStatusPanel;

