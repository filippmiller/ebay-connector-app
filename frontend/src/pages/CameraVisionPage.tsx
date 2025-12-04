/**
 * CameraVisionPage
 * 
 * Main admin page for Computer Vision module
 * Integrates DJI Osmo Pocket 3 camera with CV pipeline
 */

import React, { useState, useEffect } from 'react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card';
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
  Camera, 
  Play, 
  Square, 
  Pause,
  RefreshCw,
  Settings,
  Eye,
  FileText,
  Terminal,
  Wifi,
  WifiOff,
  Zap
} from 'lucide-react';
import { toast } from 'sonner';
import VideoPlayer from '../components/cv/VideoPlayer';
import DebugConsole from '../components/cv/DebugConsole';
import OCRLogsViewer from '../components/cv/OCRLogsViewer';
import MetricsPanel from '../components/cv/MetricsPanel';
import { cvApi, CameraInfo, CVConfig } from '../api/cv';

export const CameraVisionPage: React.FC = () => {
  const [pipelineState, setPipelineState] = useState<string>('stopped');
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<number>(0);
  const [config, setConfig] = useState<CVConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [cameraConnected, setCameraConnected] = useState(false);

  // Fetch initial state
  useEffect(() => {
    const fetchState = async () => {
      try {
        const [status, configData] = await Promise.all([
          cvApi.getStatus(),
          cvApi.getConfig(),
        ]);
        setPipelineState(status.state);
        setCameraConnected(status.camera_connected);
        setConfig(configData);
      } catch (error) {
        console.error('Failed to fetch CV state:', error);
      }
    };
    
    fetchState();
    
    // Poll for status
    const interval = setInterval(async () => {
      try {
        const status = await cvApi.getStatus();
        setPipelineState(status.state);
        setCameraConnected(status.camera_connected);
      } catch {
        // Silent fail
      }
    }, 3000);
    
    return () => clearInterval(interval);
  }, []);

  // Fetch available cameras
  const fetchCameras = async () => {
    try {
      const result = await cvApi.listCameras();
      setCameras(result.cameras);
      if (result.cameras.length > 0 && selectedCamera === 0) {
        setSelectedCamera(result.cameras[0].device_id);
      }
    } catch (error) {
      console.error('Failed to list cameras:', error);
      toast.error('Failed to detect cameras');
    }
  };

  useEffect(() => {
    fetchCameras();
  }, []);

  // Pipeline controls
  const handleStart = async () => {
    setLoading(true);
    try {
      await cvApi.startPipeline();
      setPipelineState('running');
      toast.success('CV Pipeline started');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to start pipeline');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await cvApi.stopPipeline();
      setPipelineState('stopped');
      toast.success('CV Pipeline stopped');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to stop pipeline');
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      await cvApi.pausePipeline();
      setPipelineState('paused');
      toast.info('CV Pipeline paused');
    } catch (error: any) {
      toast.error('Failed to pause pipeline');
    }
  };

  const handleResume = async () => {
    try {
      await cvApi.resumePipeline();
      setPipelineState('running');
      toast.success('CV Pipeline resumed');
    } catch (error: any) {
      toast.error('Failed to resume pipeline');
    }
  };

  // Camera controls
  const handleConnectCamera = async () => {
    setLoading(true);
    try {
      await cvApi.connectCamera({ device_id: selectedCamera });
      setCameraConnected(true);
      toast.success('Camera connected');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to connect camera');
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnectCamera = async () => {
    try {
      await cvApi.disconnectCamera();
      setCameraConnected(false);
      toast.info('Camera disconnected');
    } catch (error: any) {
      toast.error('Failed to disconnect camera');
    }
  };

  const getPipelineStateColor = (state: string) => {
    switch (state) {
      case 'running': return 'bg-green-500';
      case 'paused': return 'bg-yellow-500';
      case 'starting': return 'bg-blue-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Header */}
      <div className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Camera className="h-8 w-8 text-cyan-400" />
                <h1 className="text-2xl font-bold text-white">Computer Vision</h1>
              </div>
              <Badge className={`${getPipelineStateColor(pipelineState)} text-white`}>
                {pipelineState.toUpperCase()}
              </Badge>
            </div>
            
            {/* Pipeline Controls */}
            <div className="flex items-center gap-2">
              {pipelineState === 'stopped' ? (
                <Button 
                  onClick={handleStart} 
                  disabled={loading}
                  className="bg-green-600 hover:bg-green-700"
                >
                  <Play className="h-4 w-4 mr-2" />
                  Start Pipeline
                </Button>
              ) : pipelineState === 'running' ? (
                <>
                  <Button 
                    onClick={handlePause}
                    variant="outline"
                    className="border-yellow-500 text-yellow-500 hover:bg-yellow-500/10"
                  >
                    <Pause className="h-4 w-4 mr-2" />
                    Pause
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive">
                        <Square className="h-4 w-4 mr-2" />
                        Stop
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Stop CV Pipeline?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will stop all video processing, object detection, and OCR. 
                          The camera will be disconnected.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleStop}>
                          Stop Pipeline
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </>
              ) : pipelineState === 'paused' ? (
                <>
                  <Button 
                    onClick={handleResume}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <Play className="h-4 w-4 mr-2" />
                    Resume
                  </Button>
                  <Button variant="destructive" onClick={handleStop}>
                    <Square className="h-4 w-4 mr-2" />
                    Stop
                  </Button>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-12 gap-6">
          {/* Left Column - Video & Controls */}
          <div className="col-span-8 space-y-6">
            {/* Camera Selection & Video */}
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-white flex items-center gap-2">
                    <Camera className="h-5 w-5 text-cyan-400" />
                    DJI Osmo Pocket 3
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Select 
                      value={String(selectedCamera)} 
                      onValueChange={(v) => setSelectedCamera(Number(v))}
                    >
                      <SelectTrigger className="w-48 bg-slate-800 border-slate-700">
                        <SelectValue placeholder="Select camera" />
                      </SelectTrigger>
                      <SelectContent>
                        {cameras.length === 0 ? (
                          <SelectItem value="0">No cameras found</SelectItem>
                        ) : (
                          cameras.map((cam) => (
                            <SelectItem key={cam.device_id} value={String(cam.device_id)}>
                              {cam.name} ({cam.width}x{cam.height})
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                    
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={fetchCameras}
                      className="border-slate-700"
                    >
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                    
                    {!cameraConnected ? (
                      <Button 
                        size="sm"
                        onClick={handleConnectCamera}
                        disabled={loading || cameras.length === 0}
                        className="bg-cyan-600 hover:bg-cyan-700"
                      >
                        <Wifi className="h-4 w-4 mr-1" />
                        Connect
                      </Button>
                    ) : (
                      <Button 
                        size="sm"
                        variant="outline"
                        onClick={handleDisconnectCamera}
                        className="border-red-500 text-red-500 hover:bg-red-500/10"
                      >
                        <WifiOff className="h-4 w-4 mr-1" />
                        Disconnect
                      </Button>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-2">
                <VideoPlayer 
                  autoConnect={pipelineState === 'running'} 
                  showControls={true}
                />
              </CardContent>
            </Card>

            {/* Tabs for OCR Logs and Debug Console */}
            <Tabs defaultValue="debug" className="w-full">
              <TabsList className="bg-slate-900 border border-slate-800">
                <TabsTrigger value="debug" className="data-[state=active]:bg-slate-800">
                  <Terminal className="h-4 w-4 mr-2" />
                  Debug Console
                </TabsTrigger>
                <TabsTrigger value="ocr" className="data-[state=active]:bg-slate-800">
                  <FileText className="h-4 w-4 mr-2" />
                  OCR Results
                </TabsTrigger>
              </TabsList>
              
              <TabsContent value="debug" className="mt-4">
                <DebugConsole 
                  autoConnect={true} 
                  maxLogs={500}
                  className="h-[400px] bg-slate-900/50 border-slate-800"
                />
              </TabsContent>
              
              <TabsContent value="ocr" className="mt-4">
                <OCRLogsViewer 
                  className="bg-slate-900/50 border-slate-800"
                  limit={100}
                />
              </TabsContent>
            </Tabs>
          </div>

          {/* Right Column - Metrics & Config */}
          <div className="col-span-4 space-y-6">
            {/* Metrics Panel */}
            <MetricsPanel 
              className="bg-slate-900/50 border-slate-800"
              pollInterval={2000}
            />

            {/* Configuration Card */}
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  <Settings className="h-5 w-5 text-cyan-400" />
                  Configuration
                </CardTitle>
                <CardDescription>CV pipeline settings</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {config && (
                  <>
                    {/* Vision Settings */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-400 mb-2 flex items-center gap-1">
                        <Eye className="h-4 w-4" />
                        Vision
                      </h4>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="text-slate-500">Model</div>
                        <div className="text-white font-mono">{config.vision.yolo_model}</div>
                        <div className="text-slate-500">Confidence</div>
                        <div className="text-white font-mono">{config.vision.confidence}</div>
                        <div className="text-slate-500">Device</div>
                        <div className="text-white font-mono">{config.vision.device}</div>
                      </div>
                    </div>
                    
                    {/* OCR Settings */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-400 mb-2 flex items-center gap-1">
                        <FileText className="h-4 w-4" />
                        OCR
                      </h4>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="text-slate-500">Engine</div>
                        <div className="text-white font-mono">{config.ocr.engine}</div>
                        <div className="text-slate-500">Languages</div>
                        <div className="text-white font-mono">{config.ocr.languages.join(', ')}</div>
                        <div className="text-slate-500">Threshold</div>
                        <div className="text-white font-mono">{config.ocr.confidence_threshold}</div>
                      </div>
                    </div>
                    
                    {/* Processing Settings */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-400 mb-2 flex items-center gap-1">
                        <Zap className="h-4 w-4" />
                        Processing
                      </h4>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="text-slate-500">CV every N</div>
                        <div className="text-white font-mono">{config.processing.process_every_n_frames}</div>
                        <div className="text-slate-500">OCR every N</div>
                        <div className="text-white font-mono">{config.processing.ocr_every_n_frames}</div>
                        <div className="text-slate-500">Stream Quality</div>
                        <div className="text-white font-mono">{config.stream.quality}%</div>
                        <div className="text-slate-500">Max FPS</div>
                        <div className="text-white font-mono">{config.stream.max_fps}</div>
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Quick Info Card */}
            <Card className="bg-gradient-to-br from-cyan-900/30 to-blue-900/30 border-cyan-800/50">
              <CardHeader>
                <CardTitle className="text-cyan-400 text-base">Quick Guide</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-slate-400 space-y-2">
                <p>1. Connect your DJI Osmo Pocket 3 via USB</p>
                <p>2. Select camera and click Connect</p>
                <p>3. Start the CV Pipeline</p>
                <p>4. View real-time detections and OCR results</p>
                <p className="text-cyan-400 mt-4">
                  Tip: Use UVC mode for best quality
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CameraVisionPage;

