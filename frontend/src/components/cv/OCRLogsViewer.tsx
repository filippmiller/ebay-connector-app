/**
 * OCRLogsViewer Component
 * 
 * Displays OCR recognition results with filtering and search
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { ScrollArea } from '../ui/scroll-area';
import { Slider } from '../ui/slider';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { 
  FileText, 
  Search, 
  RefreshCw,
  Eye,
  Copy,
  CheckCircle,
  Image
} from 'lucide-react';
import { cvApi, OCRLog } from '../../api/cv';
import { toast } from 'sonner';

interface OCRLogsViewerProps {
  className?: string;
  limit?: number;
}

export const OCRLogsViewer: React.FC<OCRLogsViewerProps> = ({
  className = '',
  limit = 50,
}) => {
  const [logs, setLogs] = useState<OCRLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [minConfidence, setMinConfidence] = useState(0);
  const [selectedLog, setSelectedLog] = useState<OCRLog | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await cvApi.getOCRLogs({
        limit,
        min_confidence: minConfidence > 0 ? minConfidence : undefined,
      });
      setLogs(response.logs);
    } catch (error) {
      console.error('Failed to fetch OCR logs:', error);
      toast.error('Failed to fetch OCR logs');
    } finally {
      setLoading(false);
    }
  }, [limit, minConfidence]);

  useEffect(() => {
    fetchLogs();
    
    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchLogs, 10000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  const copyToClipboard = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
    toast.success('Copied to clipboard');
  };

  const filteredLogs = logs.filter(log => {
    if (searchTerm) {
      const search = searchTerm.toLowerCase();
      return (
        log.raw_text.toLowerCase().includes(search) ||
        log.cleaned_text?.toLowerCase().includes(search)
      );
    }
    return true;
  });

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-500';
    if (score >= 0.5) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <>
      <Card className={className}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              OCR Results
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant="outline">{filteredLogs.length} results</Badge>
              <Button 
                size="sm" 
                variant="outline" 
                onClick={fetchLogs}
                disabled={loading}
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
          
          {/* Filters */}
          <div className="flex items-center gap-4 mt-2">
            <div className="relative flex-1">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Search text..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8 h-9"
              />
            </div>
            
            <div className="flex items-center gap-2 w-48">
              <span className="text-sm text-gray-500 whitespace-nowrap">
                Min: {(minConfidence * 100).toFixed(0)}%
              </span>
              <Slider
                value={[minConfidence]}
                onValueChange={([v]) => setMinConfidence(v)}
                min={0}
                max={1}
                step={0.1}
                className="flex-1"
              />
            </div>
          </div>
        </CardHeader>
        
        <CardContent className="p-0">
          <ScrollArea className="h-[400px]">
            <Table>
              <TableHeader className="sticky top-0 bg-white dark:bg-gray-950">
                <TableRow>
                  <TableHead className="w-40">Time</TableHead>
                  <TableHead>Text</TableHead>
                  <TableHead className="w-24 text-center">Confidence</TableHead>
                  <TableHead className="w-20 text-center">Frame</TableHead>
                  <TableHead className="w-24 text-center">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredLogs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-8 text-gray-500">
                      {loading ? 'Loading...' : 'No OCR results found'}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredLogs.map((log) => (
                    <TableRow key={log.id} className="hover:bg-gray-50 dark:hover:bg-gray-900">
                      <TableCell className="text-xs text-gray-500">
                        {formatTimestamp(log.timestamp)}
                      </TableCell>
                      <TableCell>
                        <div className="max-w-md">
                          <p className="font-medium truncate">{log.cleaned_text || log.raw_text}</p>
                          {log.cleaned_text && log.raw_text !== log.cleaned_text && (
                            <p className="text-xs text-gray-400 truncate">
                              Raw: {log.raw_text}
                            </p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge 
                          variant="secondary"
                          className={`${getConfidenceColor(log.confidence_score)} text-white`}
                        >
                          {(log.confidence_score * 100).toFixed(0)}%
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center text-sm text-gray-500">
                        #{log.source_frame_number}
                      </TableCell>
                      <TableCell className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => copyToClipboard(log.cleaned_text || log.raw_text, log.id)}
                          >
                            {copied === log.id ? (
                              <CheckCircle className="h-4 w-4 text-green-500" />
                            ) : (
                              <Copy className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setSelectedLog(log)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={!!selectedLog} onOpenChange={() => setSelectedLog(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>OCR Result Details</DialogTitle>
          </DialogHeader>
          {selectedLog && (
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-500">Cleaned Text</label>
                <p className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded">
                  {selectedLog.cleaned_text || selectedLog.raw_text}
                </p>
              </div>
              
              {selectedLog.cleaned_text !== selectedLog.raw_text && (
                <div>
                  <label className="text-sm font-medium text-gray-500">Raw Text</label>
                  <p className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded font-mono text-sm">
                    {selectedLog.raw_text}
                  </p>
                </div>
              )}
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-500">Confidence</label>
                  <p className="mt-1">
                    <Badge className={getConfidenceColor(selectedLog.confidence_score)}>
                      {(selectedLog.confidence_score * 100).toFixed(1)}%
                    </Badge>
                  </p>
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-500">Frame</label>
                  <p className="mt-1">#{selectedLog.source_frame_number}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-500">Camera</label>
                  <p className="mt-1">{selectedLog.camera_id}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-500">Timestamp</label>
                  <p className="mt-1 text-sm">{formatTimestamp(selectedLog.timestamp)}</p>
                </div>
              </div>
              
              {selectedLog.crop_image_url && (
                <div>
                  <label className="text-sm font-medium text-gray-500 flex items-center gap-1">
                    <Image className="h-4 w-4" />
                    Cropped Image
                  </label>
                  <img 
                    src={selectedLog.crop_image_url} 
                    alt="OCR crop"
                    className="mt-1 max-w-full rounded border"
                  />
                </div>
              )}
              
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => copyToClipboard(selectedLog.cleaned_text || selectedLog.raw_text, 'dialog')}
                >
                  <Copy className="h-4 w-4 mr-2" />
                  Copy Text
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default OCRLogsViewer;

