import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ebayApi } from '../api/ebay';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ScrollArea } from '../components/ui/scroll-area';
import { Switch } from '../components/ui/switch';
import { Label } from '../components/ui/label';
import type { EbayConnectionStatus, EbayLog } from '../types';
import { Link as LinkIcon, Unlink } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';

export const EbayConnectionPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, refreshMe } = useAuth();
  const [connectionStatus, setConnectionStatus] = useState<EbayConnectionStatus | null>(null);
  const [logs, setLogs] = useState<EbayLog[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [environment, setEnvironment] = useState<'sandbox' | 'production'>(() => {
    const saved = localStorage.getItem('ebay_environment');
    return (saved === 'production' ? 'production' : 'sandbox') as 'sandbox' | 'production';
  });

  useEffect(() => {
    if (user?.role !== 'admin') {
      navigate('/dashboard');
      return;
    }
    loadConnectionStatus();
    loadLogs();
    const interval = setInterval(loadLogs, 3000);
    return () => clearInterval(interval);
  }, [user, navigate]);

  const loadConnectionStatus = async () => {
    try {
      const status = await ebayApi.getStatus();
      setConnectionStatus(status);
    } catch (err) {
      console.error('Failed to load connection status:', err);
    }
  };

  const loadLogs = async () => {
    try {
      const response = await ebayApi.getLogs(100);
      setLogs(response.logs);
    } catch (err) {
      console.error('Failed to load logs:', err);
    }
  };

  const handleConnectEbay = async () => {
    setError('');
    setLoading(true);

    try {
      const redirectUri = `${window.location.origin}/ebay/callback`;
      localStorage.setItem('ebay_oauth_environment', environment);
      const response = await ebayApi.startAuth(redirectUri, environment);
      window.location.href = response.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start eBay authorization');
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    setError('');
    setLoading(true);

    try {
      await ebayApi.disconnect();
      await loadConnectionStatus();
      await refreshMe();
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect from eBay');
    } finally {
      setLoading(false);
    }
  };

  const handleClearLogs = async () => {
    if (user?.role !== 'admin') {
      setError('Only admins can clear logs');
      return;
    }

    try {
      await ebayApi.clearLogs();
      await loadLogs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear logs');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'bg-green-100 text-green-800';
      case 'error':
        return 'bg-red-100 text-red-800';
      case 'info':
      default:
        return 'bg-blue-100 text-blue-800';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-16 px-4 sm:px-6 lg:px-8 py-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">eBay Connection Management</h1>

          <Tabs defaultValue="connection" className="space-y-4">
            <TabsList>
              <TabsTrigger value="connection">eBay Connection</TabsTrigger>
              <TabsTrigger value="terminal">Connection Terminal</TabsTrigger>
            </TabsList>

            <TabsContent value="connection" className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <Card>
                <CardHeader>
                  <CardTitle>eBay Connection Status</CardTitle>
                  <CardDescription>
                    Manage your eBay API connection
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border">
                    <div className="flex items-center gap-3">
                      <Label htmlFor="env-switch" className="font-medium">
                        Environment:
                      </Label>
                      <Badge variant={environment === 'sandbox' ? 'default' : 'destructive'}>
                        {environment === 'sandbox' ? 'Sandbox (Testing)' : 'Production (Live)'}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-3">
                      <Label htmlFor="env-switch" className="text-sm text-gray-600">
                        Sandbox
                      </Label>
                      <Switch
                        id="env-switch"
                        checked={environment === 'production'}
                        onCheckedChange={(checked) => {
                          const newEnv = checked ? 'production' : 'sandbox';
                          setEnvironment(newEnv);
                          localStorage.setItem('ebay_environment', newEnv);
                        }}
                        disabled={connectionStatus?.connected}
                      />
                      <Label htmlFor="env-switch" className="text-sm text-gray-600">
                        Production
                      </Label>
                    </div>
                  </div>

                  {connectionStatus?.connected && (
                    <Alert>
                      <AlertDescription>
                        Disconnect to change environment. Currently using: <strong>{environment}</strong>
                      </AlertDescription>
                    </Alert>
                  )}

                  <div className="flex items-center gap-4">
                    <div>
                      <span className="text-sm text-gray-600">Status: </span>
                      {connectionStatus?.connected ? (
                        <Badge className="bg-green-100 text-green-800">
                          <LinkIcon className="w-3 h-3 mr-1" />
                          Connected
                        </Badge>
                      ) : (
                        <Badge variant="secondary">
                          <Unlink className="w-3 h-3 mr-1" />
                          Not Connected
                        </Badge>
                      )}
                    </div>
                    {connectionStatus?.connected && connectionStatus?.expires_at && (
                      <div className="text-sm text-gray-600">
                        Expires: {new Date(connectionStatus.expires_at).toLocaleString()}
                      </div>
                    )}
                  </div>

                  <div className="pt-4 flex gap-3">
                    {connectionStatus?.connected ? (
                      <>
                        <Button 
                          onClick={() => navigate('/ebay/test')}
                          disabled={loading}
                        >
                          Test eBay API
                        </Button>
                        <Button 
                          variant="destructive" 
                          onClick={handleDisconnect}
                          disabled={loading}
                        >
                          {loading ? 'Disconnecting...' : 'Disconnect from eBay'}
                        </Button>
                      </>
                    ) : (
                      <Button 
                        onClick={handleConnectEbay}
                        disabled={loading}
                      >
                        {loading ? 'Connecting...' : 'Connect to eBay'}
                      </Button>
                    )}
                  </div>

                  <div className="pt-4 border-t">
                    <h3 className="text-sm font-medium mb-2">About eBay OAuth</h3>
                    <p className="text-sm text-gray-600">
                      To connect to eBay, you need to provide your eBay API credentials 
                      (Client ID, Client Secret, and Redirect URI) in the backend configuration.
                      Once configured, clicking "Connect to eBay" will redirect you to eBay's 
                      authorization page where you can grant access to your eBay account.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="terminal" className="space-y-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle>eBay Connection Terminal</CardTitle>
                    <CardDescription>
                      Real-time log of all eBay API credential exchanges and requests
                    </CardDescription>
                  </div>
                  <Button variant="outline" size="sm" onClick={handleClearLogs}>
                    Clear Logs
                  </Button>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-96 w-full rounded-md border bg-black text-white p-4 font-mono text-sm">
                    {logs.length === 0 ? (
                      <div className="text-gray-400">No logs yet. Connect to eBay to see credential exchanges.</div>
                    ) : (
                      <div className="space-y-2">
                        {logs.map((log, index) => (
                          <div key={index} className="pb-2 border-b border-gray-800">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-gray-500">
                                {new Date(log.timestamp).toLocaleTimeString()}
                              </span>
                              <Badge className={getStatusColor(log.status)}>
                                {log.event_type}
                              </Badge>
                              <span className="text-gray-400">{log.status}</span>
                            </div>
                            <div className="text-gray-300">{log.description}</div>
                            {log.request_data && Object.keys(log.request_data).length > 0 && (
                              <div className="mt-1 text-yellow-400">
                                → Request: {JSON.stringify(log.request_data, null, 2)}
                              </div>
                            )}
                            {log.response_data && Object.keys(log.response_data).length > 0 && (
                              <div className="mt-1 text-green-400">
                                ← Response: {JSON.stringify(log.response_data, null, 2)}
                              </div>
                            )}
                            {log.error && (
                              <div className="mt-1 text-red-400">
                                ✗ Error: {log.error}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
};
