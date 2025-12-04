/**
 * VisionBrainPage
 * 
 * Main page for the AI-powered vision brain system.
 * Combines video stream, brain instructions, and operator controls.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '../components/ui/alert-dialog';
import {
  Brain,
  Play,
  Square,
  Pause,
  Settings,
  Activity,
  History,
  Eye,
  Keyboard,
} from 'lucide-react';
import { toast } from 'sonner';

import VideoPlayer from '../components/cv/VideoPlayer';
import DebugConsole from '../components/cv/DebugConsole';
import BrainInstructionPanel from '../components/cv/BrainInstructionPanel';
import SessionTimeline from '../components/cv/SessionTimeline';
import BrainStatusPanel from '../components/cv/BrainStatusPanel';
import {
  brainApi,
  getOperatorWebSocketUrl,
  type BrainStatus,
  type SessionState,
  type HistoryEntry,
  type BrainInstruction,
} from '../api/brain';

type TaskMode = 'part_number_extraction' | 'component_identification' | 'quality_inspection' | 'inventory_scan';
type BrainMode = 'automatic' | 'semi_automatic' | 'diagnostic';

export const VisionBrainPage: React.FC = () => {
  // State
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [instruction, setInstruction] = useState<BrainInstruction | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  
  // Session config
  const [taskMode, setTaskMode] = useState<TaskMode>('part_number_extraction');
  const [brainMode, setBrainMode] = useState<BrainMode>('semi_automatic');
  const [expectedObject, setExpectedObject] = useState('');
  const [notes, setNotes] = useState('');
  const [manualInput, setManualInput] = useState('');
  
  // WebSocket ref
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch status
  const fetchStatus = useCallback(async () => {
    try {
      const [statusData, sessionData] = await Promise.all([
        brainApi.getStatus(),
        brainApi.getCurrentSession(),
      ]);
      setStatus(statusData);
      setSessionState(sessionData);
    } catch (error) {
      console.error('Failed to fetch status:', error);
    }
  }, []);

  // Connect WebSocket
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(getOperatorWebSocketUrl());
    
    ws.onopen = () => {
      setConnected(true);
      console.log('[VisionBrain] WebSocket connected');
    };
    
    ws.onclose = () => {
      setConnected(false);
      console.log('[VisionBrain] WebSocket disconnected');
      // Reconnect after delay
      setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
      console.error('[VisionBrain] WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (e) {
        console.error('[VisionBrain] Failed to parse message:', e);
      }
    };
    
    wsRef.current = ws;
  }, []);

  const handleWebSocketMessage = (data: any) => {
    switch (data.type) {
      case 'connected':
        setSessionState(data.state);
        setHistory(data.history || []);
        break;
        
      case 'brain_instruction':
        setInstruction(data as BrainInstruction);
        toast.info('Новая инструкция от мозга');
        break;
        
      case 'state_change':
        setSessionState(data.state);
        break;
        
      case 'session_started':
        setSessionState(data.state);
        toast.success('Сессия запущена');
        break;
        
      case 'session_ended':
        setSessionState(data.state);
        setInstruction(null);
        toast.info('Сессия завершена');
        break;
        
      case 'history':
        setHistory(data.history || []);
        break;
    }
  };

  // Session control
  const startSession = async () => {
    setLoading(true);
    try {
      await brainApi.startSession({
        mode: taskMode,
        expected_object_type: expectedObject || undefined,
        notes: notes || undefined,
        brain_mode: brainMode,
      });
      toast.success('Сессия запущена');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Ошибка запуска сессии');
    } finally {
      setLoading(false);
    }
  };

  const stopSession = async () => {
    setLoading(true);
    try {
      await brainApi.stopSession();
      setInstruction(null);
      toast.success('Сессия остановлена');
    } catch (error: any) {
      toast.error('Ошибка остановки сессии');
    } finally {
      setLoading(false);
    }
  };

  // Operator actions
  const handleConfirm = async () => {
    setLoading(true);
    try {
      await brainApi.submitOperatorEvent({
        event_type: 'action_confirmed',
        comment: 'Подтверждено оператором',
      });
      setInstruction(null);
    } catch (error) {
      toast.error('Ошибка подтверждения');
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await brainApi.submitOperatorEvent({
        event_type: 'action_rejected',
        comment: 'Отклонено оператором',
      });
      setInstruction(null);
    } catch (error) {
      toast.error('Ошибка отклонения');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    // Just clear instruction to wait for next brain cycle
    setInstruction(null);
  };

  const submitManualInput = async () => {
    if (!manualInput.trim()) return;
    
    try {
      await brainApi.submitManualInput('part_number', manualInput.trim());
      toast.success('Значение отправлено');
      setManualInput('');
    } catch (error) {
      toast.error('Ошибка отправки');
    }
  };

  // Effects
  useEffect(() => {
    fetchStatus();
    connectWebSocket();
    
    const interval = setInterval(fetchStatus, 5000);
    
    return () => {
      clearInterval(interval);
      wsRef.current?.close();
    };
  }, [fetchStatus, connectWebSocket]);

  // Update history when session state changes
  useEffect(() => {
    if (sessionState?.session_id) {
      brainApi.getSessionHistory().then(data => {
        setHistory(data.history);
      }).catch(() => {});
    }
  }, [sessionState?.session_id]);

  const isSessionActive = sessionState?.session_id && sessionState?.running;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950/20 to-slate-950">
      {/* Header */}
      <div className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Brain className="h-8 w-8 text-purple-400" />
                <h1 className="text-2xl font-bold text-white">Vision Brain</h1>
              </div>
              <Badge className={connected ? 'bg-green-600' : 'bg-slate-600'}>
                {connected ? 'Подключено' : 'Отключено'}
              </Badge>
              {sessionState?.session_state && (
                <Badge variant="outline" className="text-purple-400 border-purple-400">
                  {sessionState.session_state}
                </Badge>
              )}
            </div>
            
            {/* Session Controls */}
            <div className="flex items-center gap-2">
              {!isSessionActive ? (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button className="bg-purple-600 hover:bg-purple-700">
                      <Play className="h-4 w-4 mr-2" />
                      Запустить сессию
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="bg-slate-900 border-slate-700">
                    <AlertDialogHeader>
                      <AlertDialogTitle className="text-white">Настройка сессии</AlertDialogTitle>
                      <AlertDialogDescription>
                        Выберите режим работы и параметры задачи
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    
                    <div className="space-y-4 py-4">
                      <div>
                        <label className="text-sm text-slate-400 mb-1 block">Режим задачи</label>
                        <Select value={taskMode} onValueChange={(v) => setTaskMode(v as TaskMode)}>
                          <SelectTrigger className="bg-slate-800 border-slate-700">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="part_number_extraction">Извлечение Part Number</SelectItem>
                            <SelectItem value="component_identification">Идентификация компонента</SelectItem>
                            <SelectItem value="quality_inspection">Проверка качества</SelectItem>
                            <SelectItem value="inventory_scan">Сканирование инвентаря</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      
                      <div>
                        <label className="text-sm text-slate-400 mb-1 block">Режим мозга</label>
                        <Select value={brainMode} onValueChange={(v) => setBrainMode(v as BrainMode)}>
                          <SelectTrigger className="bg-slate-800 border-slate-700">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="automatic">Автоматический</SelectItem>
                            <SelectItem value="semi_automatic">Полуавтоматический</SelectItem>
                            <SelectItem value="diagnostic">Диагностический</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      
                      <div>
                        <label className="text-sm text-slate-400 mb-1 block">Ожидаемый объект</label>
                        <Input
                          value={expectedObject}
                          onChange={(e) => setExpectedObject(e.target.value)}
                          placeholder="Например: laptop_motherboard"
                          className="bg-slate-800 border-slate-700"
                        />
                      </div>
                      
                      <div>
                        <label className="text-sm text-slate-400 mb-1 block">Заметки</label>
                        <Input
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          placeholder="Дополнительные указания..."
                          className="bg-slate-800 border-slate-700"
                        />
                      </div>
                    </div>
                    
                    <AlertDialogFooter>
                      <AlertDialogCancel>Отмена</AlertDialogCancel>
                      <AlertDialogAction onClick={startSession} disabled={loading}>
                        Запустить
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              ) : (
                <>
                  <Button
                    variant="outline"
                    className="border-yellow-500 text-yellow-500 hover:bg-yellow-500/10"
                    onClick={() => brainApi.pauseSession()}
                  >
                    <Pause className="h-4 w-4 mr-2" />
                    Пауза
                  </Button>
                  <Button variant="destructive" onClick={stopSession} disabled={loading}>
                    <Square className="h-4 w-4 mr-2" />
                    Стоп
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-12 gap-6">
          {/* Left Column - Video & Instructions */}
          <div className="col-span-8 space-y-6">
            {/* Video Player */}
            <VideoPlayer autoConnect={isSessionActive} showControls={true} />
            
            {/* Brain Instructions */}
            <BrainInstructionPanel
              instruction={instruction}
              onConfirm={handleConfirm}
              onReject={handleReject}
              onRetry={handleRetry}
              loading={loading}
            />
            
            {/* Manual Input */}
            {isSessionActive && (
              <Card className="bg-slate-900/50 border-slate-700">
                <CardHeader className="pb-2">
                  <CardTitle className="text-white flex items-center gap-2 text-lg">
                    <Keyboard className="h-5 w-5 text-cyan-400" />
                    Ручной ввод
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex gap-2">
                    <Input
                      value={manualInput}
                      onChange={(e) => setManualInput(e.target.value)}
                      placeholder="Введите part number вручную..."
                      className="bg-slate-800 border-slate-700"
                      onKeyDown={(e) => e.key === 'Enter' && submitManualInput()}
                    />
                    <Button onClick={submitManualInput} disabled={!manualInput.trim()}>
                      Отправить
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Status & History */}
          <div className="col-span-4 space-y-6">
            {/* Brain Status */}
            <BrainStatusPanel
              status={status}
              sessionState={sessionState}
            />
            
            {/* Tabs for History & Debug */}
            <Tabs defaultValue="history">
              <TabsList className="bg-slate-900 border border-slate-800">
                <TabsTrigger value="history" className="data-[state=active]:bg-slate-800">
                  <History className="h-4 w-4 mr-2" />
                  История
                </TabsTrigger>
                <TabsTrigger value="debug" className="data-[state=active]:bg-slate-800">
                  <Activity className="h-4 w-4 mr-2" />
                  Логи
                </TabsTrigger>
              </TabsList>
              
              <TabsContent value="history" className="mt-4">
                <SessionTimeline history={history} />
              </TabsContent>
              
              <TabsContent value="debug" className="mt-4">
                <DebugConsole
                  autoConnect={true}
                  maxLogs={200}
                  className="h-[400px]"
                />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VisionBrainPage;

