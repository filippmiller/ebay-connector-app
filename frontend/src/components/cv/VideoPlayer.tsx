/**
 * VideoPlayer Component
 * 
 * Displays live video stream from CV module via WebSocket
 * Supports raw and annotated (with CV overlays) modes
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { 
  Play, 
  Square, 
  Maximize2, 
  Camera, 
  Layers,
  Wifi,
  WifiOff,
  Activity
} from 'lucide-react';
import { getStreamWebSocketUrl } from '../../api/cv';

interface VideoPlayerProps {
  autoConnect?: boolean;
  showControls?: boolean;
  className?: string;
}

interface FrameData {
  type: 'frame';
  frame_number: number;
  timestamp: number;
  width: number;
  height: number;
  data: string; // base64 encoded JPEG
  detections?: number;
  text_regions?: number;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  autoConnect = false,
  showControls = true,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  
  const [connected, setConnected] = useState(false);
  const [mode, setMode] = useState<'raw' | 'annotated'>('annotated');
  const [fps, setFps] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const [detections, setDetections] = useState(0);
  const [textRegions, setTextRegions] = useState(0);
  const [, setIsFullscreen] = useState(false);
  
  const fpsCounterRef = useRef({ frames: 0, lastTime: Date.now() });

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = getStreamWebSocketUrl(mode);
    const ws = new WebSocket(url);
    
    ws.onopen = () => {
      setConnected(true);
      console.log('[VideoPlayer] Connected to stream');
    };
    
    ws.onclose = () => {
      setConnected(false);
      console.log('[VideoPlayer] Disconnected from stream');
    };
    
    ws.onerror = (error) => {
      console.error('[VideoPlayer] WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
      try {
        const data: FrameData = JSON.parse(event.data);
        
        if (data.type === 'frame') {
          renderFrame(data);
          
          // Update stats
          setFrameCount(data.frame_number);
          if (data.detections !== undefined) setDetections(data.detections);
          if (data.text_regions !== undefined) setTextRegions(data.text_regions);
          
          // Calculate FPS
          fpsCounterRef.current.frames++;
          const now = Date.now();
          if (now - fpsCounterRef.current.lastTime >= 1000) {
            setFps(fpsCounterRef.current.frames);
            fpsCounterRef.current.frames = 0;
            fpsCounterRef.current.lastTime = now;
          }
        }
      } catch (e) {
        console.error('[VideoPlayer] Failed to parse message:', e);
      }
    };
    
    wsRef.current = ws;
  }, [mode]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const renderFrame = (data: FrameData) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const img = new Image();
    img.onload = () => {
      // Resize canvas if needed
      if (canvas.width !== data.width || canvas.height !== data.height) {
        canvas.width = data.width;
        canvas.height = data.height;
      }
      ctx.drawImage(img, 0, 0);
    };
    img.src = `data:image/jpeg;base64,${data.data}`;
  };

  const toggleMode = () => {
    const newMode = mode === 'raw' ? 'annotated' : 'raw';
    setMode(newMode);
    
    // Reconnect with new mode
    if (connected) {
      disconnect();
      setTimeout(() => connect(), 100);
    }
  };

  const toggleFullscreen = () => {
    const container = canvasRef.current?.parentElement;
    if (!container) return;
    
    if (!document.fullscreenElement) {
      container.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  return (
    <Card className={`overflow-hidden ${className}`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Camera className="h-5 w-5" />
            Live Video Stream
          </CardTitle>
          <div className="flex items-center gap-2">
            {connected ? (
              <Badge variant="default" className="bg-green-600">
                <Wifi className="h-3 w-3 mr-1" />
                Connected
              </Badge>
            ) : (
              <Badge variant="secondary">
                <WifiOff className="h-3 w-3 mr-1" />
                Disconnected
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="p-0">
        {/* Video Container */}
        <div className="relative bg-black aspect-video">
          <canvas
            ref={canvasRef}
            className="w-full h-full object-contain"
          />
          
          {/* Overlay Stats */}
          {connected && (
            <div className="absolute top-2 left-2 flex flex-col gap-1">
              <Badge variant="secondary" className="text-xs bg-black/70">
                <Activity className="h-3 w-3 mr-1" />
                {fps} FPS
              </Badge>
              <Badge variant="secondary" className="text-xs bg-black/70">
                Frame: {frameCount}
              </Badge>
              {mode === 'annotated' && (
                <>
                  <Badge variant="secondary" className="text-xs bg-black/70">
                    Objects: {detections}
                  </Badge>
                  <Badge variant="secondary" className="text-xs bg-black/70">
                    Text: {textRegions}
                  </Badge>
                </>
              )}
            </div>
          )}
          
          {/* Not Connected Overlay */}
          {!connected && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80">
              <div className="text-center text-white">
                <Camera className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <p className="text-lg mb-4">No video stream</p>
                <Button onClick={connect} variant="secondary">
                  <Play className="h-4 w-4 mr-2" />
                  Connect
                </Button>
              </div>
            </div>
          )}
        </div>
        
        {/* Controls */}
        {showControls && (
          <div className="p-3 bg-gray-100 dark:bg-gray-900 border-t flex items-center justify-between">
            <div className="flex items-center gap-2">
              {!connected ? (
                <Button size="sm" onClick={connect} className="gap-1">
                  <Play className="h-4 w-4" />
                  Connect
                </Button>
              ) : (
                <Button size="sm" variant="destructive" onClick={disconnect} className="gap-1">
                  <Square className="h-4 w-4" />
                  Disconnect
                </Button>
              )}
              
              <Button
                size="sm"
                variant={mode === 'annotated' ? 'default' : 'outline'}
                onClick={toggleMode}
                className="gap-1"
              >
                <Layers className="h-4 w-4" />
                {mode === 'annotated' ? 'CV On' : 'CV Off'}
              </Button>
            </div>
            
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={toggleFullscreen}>
                <Maximize2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default VideoPlayer;

