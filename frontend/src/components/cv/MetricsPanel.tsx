/**
 * MetricsPanel Component
 * 
 * Real-time metrics display for CV module
 * Shows FPS, processing stats, and component health
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Progress } from '../ui/progress';
import { 
  Activity, 
  Cpu, 
  Eye, 
  FileText,
  Database,
  Camera,
  Zap,
  AlertCircle
} from 'lucide-react';
import { cvApi, CVMetrics, PipelineStats } from '../../api/cv';

interface MetricsPanelProps {
  className?: string;
  pollInterval?: number;
}

interface ComponentStatus {
  name: string;
  icon: React.ReactNode;
  status: string;
  color: string;
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({
  className = '',
  pollInterval = 2000,
}) => {
  const [metrics, setMetrics] = useState<CVMetrics | null>(null);
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMetrics = useCallback(async () => {
    try {
      const [metricsData, statusData] = await Promise.all([
        cvApi.getMetrics(),
        cvApi.getStatus(),
      ]);
      setMetrics(metricsData);
      setStats(statusData.stats);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, pollInterval);
    return () => clearInterval(interval);
  }, [fetchMetrics, pollInterval]);

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'connected':
      case 'ready':
      case 'streaming':
      case 'running':
        return 'bg-green-500';
      case 'connecting':
      case 'starting':
        return 'bg-yellow-500';
      case 'disconnected':
      case 'stopped':
      case 'not_initialized':
        return 'bg-gray-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const components: ComponentStatus[] = metrics ? [
    {
      name: 'Camera',
      icon: <Camera className="h-4 w-4" />,
      status: metrics.camera_status,
      color: getStatusColor(metrics.camera_status),
    },
    {
      name: 'Vision',
      icon: <Eye className="h-4 w-4" />,
      status: metrics.cv_status,
      color: getStatusColor(metrics.cv_status),
    },
    {
      name: 'OCR',
      icon: <FileText className="h-4 w-4" />,
      status: metrics.ocr_status,
      color: getStatusColor(metrics.ocr_status),
    },
    {
      name: 'Database',
      icon: <Database className="h-4 w-4" />,
      status: metrics.supabase_status,
      color: getStatusColor(metrics.supabase_status),
    },
  ] : [];

  if (loading) {
    return (
      <Card className={className}>
        <CardContent className="p-6 text-center text-gray-500">
          Loading metrics...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Activity className="h-5 w-5" />
          System Metrics
        </CardTitle>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Pipeline State */}
        {stats && (
          <div className="flex items-center justify-between p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-yellow-500" />
              <span className="font-medium">Pipeline</span>
            </div>
            <Badge className={getStatusColor(stats.state)}>
              {stats.state.toUpperCase()}
            </Badge>
          </div>
        )}
        
        {/* Component Status Grid */}
        <div className="grid grid-cols-2 gap-2">
          {components.map((comp) => (
            <div
              key={comp.name}
              className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900 rounded"
            >
              <div className="flex items-center gap-2">
                {comp.icon}
                <span className="text-sm">{comp.name}</span>
              </div>
              <div className={`w-2 h-2 rounded-full ${comp.color}`} />
            </div>
          ))}
        </div>
        
        {/* Performance Metrics */}
        {metrics && (
          <div className="space-y-3">
            {/* FPS */}
            <div>
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="text-gray-500">FPS</span>
                <span className="font-mono font-medium">{metrics.fps.toFixed(1)}</span>
              </div>
              <Progress value={Math.min(metrics.fps / 30 * 100, 100)} className="h-2" />
            </div>
            
            {/* Frames Processed */}
            <div className="flex items-center justify-between py-2 border-t">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-500">Frames Processed</span>
              </div>
              <span className="font-mono text-sm">{metrics.frames_processed.toLocaleString()}</span>
            </div>
            
            {/* OCR Count */}
            <div className="flex items-center justify-between py-2 border-t">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-500">OCR Results</span>
              </div>
              <span className="font-mono text-sm">{metrics.ocr_count.toLocaleString()}</span>
            </div>
            
            {/* Errors */}
            <div className="flex items-center justify-between py-2 border-t">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-500">Errors</span>
              </div>
              <Badge variant={metrics.errors > 0 ? 'destructive' : 'secondary'}>
                {metrics.errors}
              </Badge>
            </div>
          </div>
        )}
        
        {/* Stats Details */}
        {stats && (
          <div className="pt-2 border-t space-y-2">
            <div className="text-xs text-gray-500 uppercase font-medium">Processing Stats</div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Uptime</span>
                <span className="font-mono">{Math.floor(stats.uptime_seconds / 60)}m</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Avg FPS</span>
                <span className="font-mono">{stats.avg_fps.toFixed(1)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">CV Time</span>
                <span className="font-mono">{stats.avg_cv_time_ms.toFixed(1)}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">OCR Time</span>
                <span className="font-mono">{stats.avg_ocr_time_ms.toFixed(1)}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Detections</span>
                <span className="font-mono">{stats.detections_total.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">OCR Results</span>
                <span className="font-mono">{stats.ocr_results_total.toLocaleString()}</span>
              </div>
            </div>
          </div>
        )}
        
        {/* Last Error */}
        {metrics?.last_error && (
          <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
            <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm font-medium mb-1">
              <AlertCircle className="h-4 w-4" />
              Last Error
            </div>
            <p className="text-sm text-red-700 dark:text-red-300">
              [{metrics.last_error.subsystem}] {metrics.last_error.message}
            </p>
            <p className="text-xs text-red-500 mt-1">
              {new Date(metrics.last_error.timestamp).toLocaleString()}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default MetricsPanel;

