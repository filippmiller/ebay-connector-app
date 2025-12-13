/**
 * BrainInstructionPanel Component
 * 
 * Displays instructions from the AI brain and provides
 * action buttons for operator responses.
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Progress } from '../ui/progress';
import {
  Brain,
  Check,
  X,
  RefreshCw,
  Lightbulb,
  AlertCircle,
  MessageSquare,
} from 'lucide-react';
import type { BrainInstruction } from '../../api/brain';

interface BrainInstructionPanelProps {
  instruction: BrainInstruction | null;
  onConfirm: () => void;
  onReject: () => void;
  onRetry: () => void;
  loading?: boolean;
  className?: string;
}

export const BrainInstructionPanel: React.FC<BrainInstructionPanelProps> = ({
  instruction,
  onConfirm,
  onReject,
  onRetry,
  loading = false,
  className = '',
}) => {
  if (!instruction) {
    return (
      <Card className={`${className} bg-slate-900/50 border-slate-700`}>
        <CardContent className="py-12 text-center">
          <Brain className="h-16 w-16 mx-auto mb-4 text-slate-600" />
          <p className="text-slate-500">Ожидание инструкций от мозга...</p>
          <p className="text-sm text-slate-600 mt-2">
            Положите деталь на стол и запустите сессию
          </p>
        </CardContent>
      </Card>
    );
  }

  const getDecisionIcon = () => {
    switch (instruction.decision_type) {
      case 'final_result':
        return <Check className="h-5 w-5 text-green-400" />;
      case 'clarification_needed':
        return <AlertCircle className="h-5 w-5 text-yellow-400" />;
      default:
        return <Lightbulb className="h-5 w-5 text-cyan-400" />;
    }
  };

  const getDecisionColor = () => {
    switch (instruction.decision_type) {
      case 'final_result':
        return 'bg-green-600';
      case 'clarification_needed':
        return 'bg-yellow-600';
      case 'error':
        return 'bg-red-600';
      default:
        return 'bg-cyan-600';
    }
  };

  return (
    <Card className={`${className} bg-slate-900/50 border-slate-700`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-white flex items-center gap-2">
            <Brain className="h-5 w-5 text-purple-400" />
            Инструкции мозга
          </CardTitle>
          <Badge className={getDecisionColor()}>
            {getDecisionIcon()}
            <span className="ml-1 capitalize">{instruction.decision_type.replace('_', ' ')}</span>
          </Badge>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Main Instructions */}
        <div className="space-y-2">
          {instruction.messages.map((message, i) => (
            <div
              key={i}
              className="p-3 bg-slate-800 rounded-lg border border-slate-700"
            >
              <div className="flex items-start gap-2">
                <MessageSquare className="h-5 w-5 text-cyan-400 mt-0.5 shrink-0" />
                <p className="text-white">{message}</p>
              </div>
            </div>
          ))}
        </div>
        
        {/* Extracted Values */}
        {instruction.extracted_values.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-slate-400">Найденные значения:</h4>
            {instruction.extracted_values.map((val, i) => (
              <div
                key={i}
                className="p-3 bg-green-900/30 rounded-lg border border-green-700"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs text-green-400 uppercase">{val.type}</span>
                    <p className="text-lg font-mono text-white">{val.value}</p>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-slate-400">Уверенность</span>
                    <p className="text-lg font-bold text-green-400">
                      {(val.confidence * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>
                <Progress value={val.confidence * 100} className="mt-2 h-1" />
              </div>
            ))}
          </div>
        )}
        
        {/* Comments */}
        {instruction.comments && (
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-sm text-slate-400">{instruction.comments}</p>
          </div>
        )}
        
        {/* Confidence */}
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Общая уверенность:</span>
          <div className="flex items-center gap-2">
            <Progress value={instruction.confidence * 100} className="w-24 h-2" />
            <span className="text-white font-medium">
              {(instruction.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
        
        {/* Action Buttons */}
        <div className="flex gap-2 pt-2">
          <Button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 bg-green-600 hover:bg-green-700"
          >
            <Check className="h-4 w-4 mr-2" />
            Подтвердить
          </Button>
          <Button
            onClick={onReject}
            disabled={loading}
            variant="outline"
            className="flex-1 border-red-500 text-red-500 hover:bg-red-500/10"
          >
            <X className="h-4 w-4 mr-2" />
            Отклонить
          </Button>
          <Button
            onClick={onRetry}
            disabled={loading}
            variant="outline"
            className="border-slate-600"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default BrainInstructionPanel;

