import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ebayApi } from '../api/ebay';
import api from '../lib/apiClient';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ScrollArea } from '../components/ui/scroll-area';
import { Switch } from '../components/ui/switch';
import { Label } from '../components/ui/label';
import { SyncTerminal } from '../components/SyncTerminal';
import { EbayDebugger } from '../components/EbayDebugger';
import type { EbayConnectionStatus, EbayLog, EbayConnectLog } from '../types';
import { Link as LinkIcon, Unlink, Loader2 } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';

const DEFAULT_SCOPES = [
  'https://api.ebay.com/oauth/api_scope',
  'https://api.ebay.com/oauth/api_scope/sell.account',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
  'https://api.ebay.com/oauth/api_scope/sell.finances',
  'https://api.ebay.com/oauth/api_scope/sell.inventory',
];

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
  
  const [syncing, setSyncing] = useState(false);
  const [syncingTransactions, setSyncingTransactions] = useState(false);
  const [syncingDisputes, setSyncingDisputes] = useState(false);
  const [syncingMessages, setSyncingMessages] = useState(false);
  const [syncingOffers, setSyncingOffers] = useState(false);
  const [ordersRunId, setOrdersRunId] = useState<string | null>(null);
  const [transactionsRunId, setTransactionsRunId] = useState<string | null>(null);
  const [disputesRunId, setDisputesRunId] = useState<string | null>(null);
  const [messagesRunId, setMessagesRunId] = useState<string | null>(null);
  const [offersRunId, setOffersRunId] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<any>(null);
  const [transactionsSyncResult, setTransactionsSyncResult] = useState<any>(null);
  const [disputesSyncResult, setDisputesSyncResult] = useState<any>(null);
  const [messagesSyncResult, setMessagesSyncResult] = useState<any>(null);
  const [offersSyncResult, setOffersSyncResult] = useState<any>(null);
  const [connectLogs, setConnectLogs] = useState<EbayConnectLog[]>([]);
  const [connectLogLoading, setConnectLogLoading] = useState(false);
  const [connectLogError, setConnectLogError] = useState('');

  useEffect(() => {
    if (user?.role !== 'admin') {
      navigate('/dashboard');
      return;
    }
    loadConnectionStatus();
    loadLogs();
    const interval = setInterval(loadLogs, 3000);
    return () => {
      clearInterval(interval);
    };
  }, [user, navigate]);

  useEffect(() => {
    if (user?.role !== 'admin') return;
    loadConnectLogs(environment);
    const interval = setInterval(() => loadConnectLogs(environment), 5000);
    return () => clearInterval(interval);
  }, [environment, user]);

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

  const loadConnectLogs = async (env: 'sandbox' | 'production') => {
    try {
      setConnectLogLoading(true);
      const response = await ebayApi.getConnectLogs(env, 100);
      setConnectLogs(response.logs);
      setConnectLogError('');
    } catch (err) {
      console.error('Failed to load connection logs:', err);
      setConnectLogError('Failed to load connection logs');
    } finally {
      setConnectLogLoading(false);
    }
  };

  // Export helpers for Connection Terminal
  const exportConnectLogs = (format: 'json' | 'ndjson' | 'txt') => {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const filenameBase = `connect_logs_${environment}_${ts}`;

    let blob: Blob;
    if (format === 'json') {
      blob = new Blob([JSON.stringify({ logs: connectLogs }, null, 2)], { type: 'application/json' });
      triggerDownload(`${filenameBase}.json`, blob);
      return;
    }
    if (format === 'ndjson') {
      const nd = connectLogs.map(l => JSON.stringify(l)).join('\n');
      blob = new Blob([nd], { type: 'application/x-ndjson' });
      triggerDownload(`${filenameBase}.ndjson`, blob);
      return;
    }
    // txt (pretty)
    const txt = connectLogs.map(l => {
      const lines: string[] = [];
      lines.push(`[${new Date(l.created_at).toISOString()}] ${l.environment} • ${l.action}`);
      if (l.request) {
        lines.push(`→ ${l.request.method || ''} ${l.request.url || ''}`);
        if (l.request.headers) lines.push(`headers: ${JSON.stringify(l.request.headers)}`);
        if (l.request.body) lines.push(`body: ${typeof l.request.body === 'string' ? l.request.body : JSON.stringify(l.request.body)}`);
      }
      if (l.response) {
        lines.push(`← status: ${l.response.status ?? ''}`);
        if (l.response.headers) lines.push(`resp-headers: ${JSON.stringify(l.response.headers)}`);
        if (typeof l.response.body !== 'undefined') lines.push(`resp-body: ${typeof l.response.body === 'string' ? l.response.body : JSON.stringify(l.response.body)}`);
      }
      if (l.error) lines.push(`error: ${l.error}`);
      return lines.join('\n');
    }).join('\n\n');
    blob = new Blob([txt], { type: 'text/plain' });
    triggerDownload(`${filenameBase}.txt`, blob);
  };

  const triggerDownload = (filename: string, blob: Blob) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
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

  const handleSyncOrders = async () => {
    if (syncing || ordersRunId) {
      setError('Sync already in progress. Please wait or stop the current sync.');
      return;
    }
    setError('');
    setSyncing(true);
    setSyncResult(null);
    setOrdersRunId(null);
    try {
      const data = await ebayApi.syncAllOrders(environment);
      setSyncResult(data);
      if (data.run_id) {
        setOrdersRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync orders');
      setSyncing(false);
    }
  };

  const handleSyncTransactions = async () => {
    if (syncingTransactions || transactionsRunId) {
      setError('Sync already in progress. Please wait or stop the current sync.');
      return;
    }
    setError('');
    setSyncingTransactions(true);
    setTransactionsSyncResult(null);
    setTransactionsRunId(null);
    try {
      const data = await ebayApi.syncAllTransactions(environment);
      setTransactionsSyncResult(data);
      if (data.run_id) {
        setTransactionsRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync transactions');
      setSyncingTransactions(false);
    }
  };

  const handleSyncDisputes = async () => {
    if (syncingDisputes || disputesRunId) {
      setError('Sync already in progress. Please wait or stop the current sync.');
      return;
    }
    setError('');
    setSyncingDisputes(true);
    setDisputesSyncResult(null);
    setDisputesRunId(null);
    try {
      const data = await ebayApi.syncAllDisputes(environment);
      setDisputesSyncResult(data);
      if (data.run_id) {
        setDisputesRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync disputes');
      setSyncingDisputes(false);
    }
  };

  const handleSyncMessages = async () => {
    if (syncingMessages || messagesRunId) {
      setError('Sync already in progress. Please wait or stop the current sync.');
      return;
    }
    setError('');
    setSyncingMessages(true);
    setMessagesSyncResult(null);
    setMessagesRunId(null);
    try {
      const response = await api.post('/messages/sync');
      setMessagesSyncResult(response.data);
      if (response.data.run_id) {
        setMessagesRunId(response.data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync messages');
      setSyncingMessages(false);
    }
  };

  const handleSyncOffers = async () => {
    if (syncingOffers || offersRunId) {
      setError('Sync already in progress. Please wait or stop the current sync.');
      return;
    }
    setError('');
    setSyncingOffers(true);
    setOffersSyncResult(null);
    setOffersRunId(null);
    try {
      const data = await ebayApi.syncAllOffers(environment);
      setOffersSyncResult(data);
      if (data.run_id) {
        setOffersRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync offers');
      setSyncingOffers(false);
    }
  };

  const handleSyncComplete = (type: string, doneEvent?: any) => {
    // Extract counts from done event if available
    if (doneEvent) {
      const fetched = doneEvent.extra_data?.total_fetched ?? doneEvent.extra_data?.fetched ?? 0;
      const stored = doneEvent.extra_data?.total_stored ?? doneEvent.extra_data?.stored ?? 0;
      const job_id = doneEvent.extra_data?.job_id ?? null;
      
      switch (type) {
        case 'orders':
          setSyncResult({ total_fetched: fetched, total_stored: stored, job_id });
          break;
        case 'messages':
          setMessagesSyncResult({ total_fetched: fetched, total_stored: stored });
          break;
        case 'transactions':
          setTransactionsSyncResult({ total_fetched: fetched, total_stored: stored });
          break;
        case 'disputes':
          setDisputesSyncResult({ total_fetched: fetched, total_stored: stored });
          break;
        case 'offers':
          setOffersSyncResult({ total_fetched: fetched, total_stored: stored });
          break;
      }
    }
    
    switch (type) {
      case 'orders':
        setSyncing(false);
        break;
      case 'transactions':
        setSyncingTransactions(false);
        break;
      case 'disputes':
        setSyncingDisputes(false);
        break;
      case 'messages':
        setSyncingMessages(false);
        break;
      case 'offers':
        setSyncingOffers(false);
        break;
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

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString(undefined, { hour12: false });
    } catch {
      return timestamp;
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
              <TabsTrigger value="sync">Sync Data</TabsTrigger>
              <TabsTrigger value="debugger">🔧 API Debugger</TabsTrigger>
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

              <Card>
                <CardHeader>
                  <CardTitle>Connection Request Preview</CardTitle>
                  <CardDescription>
                    Preview of the authorization request that will be sent to eBay for the selected environment.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <h4 className="text-sm font-semibold">Environment</h4>
                      <Badge variant={environment === 'sandbox' ? 'default' : 'destructive'}>
                        {environment === 'sandbox' ? '🧪 Sandbox' : '🚀 Production'}
                      </Badge>
                      <div className="text-xs text-gray-500">
                        Redirect URI:{' '}
                        <span className="font-mono">
                          {typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback'}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div><span className="font-semibold text-gray-700">Method:</span> GET</div>
                      <div>
                        <span className="font-semibold text-gray-700">URL:</span>{' '}
                        <span className="font-mono text-blue-600 break-all">
                          {environment === 'production'
                            ? 'https://auth.ebay.com/oauth2/authorize'
                            : 'https://auth.sandbox.ebay.com/oauth2/authorize'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4">
                    <h4 className="text-sm font-semibold mb-2">Query Parameters</h4>
                    <ScrollArea className="h-32 rounded border bg-gray-50 p-3 text-xs font-mono">
                      {Array.from(
                        new URLSearchParams({
                          response_type: 'code',
                          redirect_uri: typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback',
                          scope: DEFAULT_SCOPES.join(' '),
                          state: 'generated server-side',
                        }).entries()
                      ).map(([key, value]) => (
                        <div key={key} className="text-gray-700">
                          {key}: <span className="text-gray-900">{value}</span>
                        </div>
                      ))}
                    </ScrollArea>
                    <div className="mt-3">
                      <h4 className="text-sm font-semibold mb-2">Raw Authorization URL</h4>
                      <div className="p-2 bg-gray-50 border rounded font-mono text-xs break-all">
                        {(() => {
                          const base = environment === 'production' ? 'https://auth.ebay.com/oauth2/authorize' : 'https://auth.sandbox.ebay.com/oauth2/authorize';
                          const qs = new URLSearchParams({
                            response_type: 'code',
                            redirect_uri: typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback',
                            scope: DEFAULT_SCOPES.join(' '),
                            state: 'generated server-side',
                            client_id: 'configured server-side'
                          }).toString();
                          return `GET ${base}?${qs}`;
                        })()}
                      </div>
                      <p className="text-xs text-gray-500 mt-2">Actual values (client_id/state) задаются сервером и логируются в “Connection Terminal”.</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                  <CardHeader>
                  <CardTitle>Connection Terminal</CardTitle>
                  <CardDescription>
                    Real-time history of connect requests and responses. Data is stored in the database for diagnostics.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between mb-2">
                    {connectLogError ? (
                      <Alert variant="destructive" className="mr-3">
                        <AlertDescription>{connectLogError}</AlertDescription>
                      </Alert>
                    ) : (
                      <div className="text-sm text-gray-600" />
                    )}
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" onClick={() => exportConnectLogs('json')}>Save JSON</Button>
                      <Button size="sm" variant="outline" onClick={() => exportConnectLogs('ndjson')}>Save NDJSON</Button>
                      <Button size="sm" variant="outline" onClick={() => exportConnectLogs('txt')}>Save TXT</Button>
                    </div>
                  </div>
                  {connectLogLoading && (
                    <div className="flex items-center text-sm text-gray-600 mb-2">
                      <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading connection logs...
                    </div>
                  )}
                  <ScrollArea className="h-80 rounded border bg-gray-900 p-4 text-xs font-mono">
                    {connectLogs.length === 0 ? (
                      <div className="text-gray-400">
                        No connection events yet. Click "Connect to eBay" to generate logs.
                      </div>
                    ) : (
                      connectLogs.map((log) => (
                        <div key={log.id} className="border-b border-gray-800 pb-4 mb-4 last:border-0 last:pb-0 last:mb-0">
                          <div className="flex flex-wrap items-center justify-between text-gray-400">
                            <span>[{new Date(log.created_at).toLocaleString()}]</span>
                            <span>{log.environment === 'sandbox' ? '🧪 Sandbox' : '🚀 Production'} • {log.action}</span>
                          </div>
                          {log.request && (
                            <div className="mt-2">
                              <div className="text-green-400 font-semibold">→ REQUEST</div>
                              <div className="text-green-200 mt-1 overflow-x-auto">
                                {log.request.method} {log.request.url}
                              </div>
                              {log.request.headers && (
                                <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-32 text-green-100 whitespace-pre-wrap break-words">
                                  {JSON.stringify(log.request.headers, null, 2)}
                                </pre>
                              )}
                              {log.request.body && (
                                <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-32 text-green-100 whitespace-pre-wrap break-words">
                                  {typeof log.request.body === 'string' ? log.request.body : JSON.stringify(log.request.body, null, 2)}
                                </pre>
                              )}
                            </div>
                          )}
                          {log.response && (
                            <div className="mt-2">
                              <div className={`font-semibold ${log.response.status && log.response.status >= 200 && log.response.status < 300 ? 'text-blue-300' : 'text-red-300'}`}>
                                ← RESPONSE {log.response.status ?? ''}
                              </div>
                              {log.response.headers && (
                                <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-32 text-blue-100 whitespace-pre-wrap break-words">
                                  {JSON.stringify(log.response.headers, null, 2)}
                                </pre>
                              )}
                              {typeof log.response.body !== 'undefined' && (
                                <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-48 text-blue-100 whitespace-pre-wrap break-words">
                                  {typeof log.response.body === 'string' ? log.response.body : JSON.stringify(log.response.body, null, 2)}
                                </pre>
                              )}
                            </div>
                          )}
                          {log.error && (
                            <div className="mt-2 text-red-400">⚠️ {log.error}</div>
                          )}
                        </div>
                      ))
                    )}
                  </ScrollArea>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="sync" className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {!connectionStatus?.connected && (
                <Alert>
                  <AlertDescription>
                    Please connect to eBay first to sync data.
                  </AlertDescription>
                </Alert>
              )}

              <Card>
                <CardHeader>
                  <CardTitle>Sync Operations</CardTitle>
                  <CardDescription>
                    Fetch data from eBay and store in database
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="mb-4 p-3 bg-gray-50 rounded-lg border">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-700">Environment:</span>
                      <Badge variant={environment === 'sandbox' ? 'default' : 'destructive'}>
                        {environment === 'sandbox' ? '🧪 Sandbox (Testing)' : '🚀 Production (Live)'}
                      </Badge>
                      <span className="text-xs text-gray-500">
                        All sync operations will use {environment} environment
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      onClick={handleSyncOrders}
                      disabled={syncing || !connectionStatus?.connected}
                      size="sm"
                    >
                      {syncing ? 'Syncing...' : 'Orders'}
                    </Button>
                    <Button
                      onClick={handleSyncTransactions}
                      disabled={syncingTransactions || !connectionStatus?.connected}
                      size="sm"
                      variant="secondary"
                    >
                      {syncingTransactions ? 'Syncing...' : 'Transactions'}
                    </Button>
                    <Button
                      onClick={handleSyncDisputes}
                      disabled={syncingDisputes || !connectionStatus?.connected}
                      size="sm"
                      variant="secondary"
                    >
                      {syncingDisputes ? 'Syncing...' : 'Disputes'}
                    </Button>
                    <Button
                      onClick={handleSyncMessages}
                      disabled={syncingMessages || !connectionStatus?.connected}
                      size="sm"
                      variant="secondary"
                    >
                      {syncingMessages ? 'Syncing...' : 'Messages'}
                    </Button>
                    <Button
                      onClick={handleSyncOffers}
                      disabled={syncingOffers || !connectionStatus?.connected}
                      size="sm"
                      variant="secondary"
                    >
                      {syncingOffers ? 'Syncing...' : 'Offers'}
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {ordersRunId && (
                <div className="mt-6">
                  <SyncTerminal 
                    runId={ordersRunId}
                    onComplete={(doneEvent) => handleSyncComplete('orders', doneEvent)}
                    onStop={() => setSyncing(false)}
                  />
                </div>
              )}

              {transactionsRunId && (
                <div className="mt-6">
                  <SyncTerminal 
                    runId={transactionsRunId}
                    onComplete={(doneEvent) => handleSyncComplete('transactions', doneEvent)}
                    onStop={() => setSyncingTransactions(false)}
                  />
                </div>
              )}

              {disputesRunId && (
                <div className="mt-6">
                  <SyncTerminal 
                    runId={disputesRunId}
                    onComplete={(doneEvent) => handleSyncComplete('disputes', doneEvent)}
                    onStop={() => setSyncingDisputes(false)}
                  />
                </div>
              )}

              {messagesRunId && (
                <div className="mt-6">
                  <SyncTerminal 
                    runId={messagesRunId}
                    onComplete={(doneEvent) => {
                      handleSyncComplete('messages', doneEvent);
                      // DO NOT clear runId - keep terminal visible so user can view logs
                    }}
                    onStop={() => {
                      setSyncingMessages(false);
                      // DO NOT clear runId - keep terminal visible even after stop
                    }}
                  />
                </div>
              )}

              {offersRunId && (
                <div className="mt-6">
                  <SyncTerminal 
                    runId={offersRunId}
                    onComplete={(doneEvent) => {
                      handleSyncComplete('offers', doneEvent);
                      // DO NOT clear runId - keep terminal visible so user can view logs
                    }}
                    onStop={() => {
                      setSyncingOffers(false);
                      // DO NOT clear runId - keep terminal visible even after stop
                    }}
                  />
                </div>
              )}

              {syncResult && (
                <Alert className="mt-6 bg-green-50 border-green-200">
                  <AlertDescription className="text-green-800">
                    <strong>Orders Synced!</strong>
                    <div className="mt-2 space-y-1">
                      <div>Total Fetched: {syncResult.total_fetched}</div>
                      <div>Total Stored: {syncResult.total_stored}</div>
                      <div>Job ID: {syncResult.job_id}</div>
                    </div>
                  </AlertDescription>
                </Alert>
              )}

              {transactionsSyncResult && (
                <Alert className="mt-6 bg-blue-50 border-blue-200">
                  <AlertDescription className="text-blue-800">
                    <strong>Transactions Synced!</strong> Fetched: {transactionsSyncResult.total_fetched}, Stored: {transactionsSyncResult.total_stored}
                  </AlertDescription>
                </Alert>
              )}

              {disputesSyncResult && (
                <Alert className="mt-6 bg-purple-50 border-purple-200">
                  <AlertDescription className="text-purple-800">
                    <strong>Disputes Synced!</strong> Fetched: {disputesSyncResult.total_fetched}, Stored: {disputesSyncResult.total_stored}
                  </AlertDescription>
                </Alert>
              )}

              {messagesSyncResult && (
                <Alert className="mt-6 bg-indigo-50 border-indigo-200">
                  <AlertDescription className="text-indigo-800">
                    <strong>Messages Synced!</strong> Fetched: {messagesSyncResult.total_fetched}, Stored: {messagesSyncResult.total_stored}
                  </AlertDescription>
                </Alert>
              )}

              {offersSyncResult && (
                <Alert className="mt-6 bg-orange-50 border-orange-200">
                  <AlertDescription className="text-orange-800">
                    <strong>Offers Synced!</strong> Fetched: {offersSyncResult.total_fetched}, Stored: {offersSyncResult.total_stored}
                  </AlertDescription>
                </Alert>
              )}
            </TabsContent>

            <TabsContent value="debugger" className="space-y-4">
              <EbayDebugger />
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
                                {formatTimestamp(log.timestamp)}
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
