import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ebayApi } from '../api/ebay';
import api from '../lib/apiClient';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ScrollArea } from '../components/ui/scroll-area';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { SyncTerminal } from '../components/SyncTerminal';
import { EbayDebugger } from '../components/EbayDebugger';
import type { EbayConnectionStatus, EbayLog, EbayConnectLog } from '../types';
import { Link as LinkIcon, Loader2 } from 'lucide-react';
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
  // For now operate only against production environment on this page
  const [environment] = useState<'sandbox' | 'production'>('production');
  
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
  // Connection Terminal UX
  const [connWrap, setConnWrap] = useState<boolean>(false);
  const [connectSearch, setConnectSearch] = useState<string>('');
  const [terminalSearch, setTerminalSearch] = useState<string>('');

  // Available scopes loaded from backend catalog
  const [availableScopes, setAvailableScopes] = useState<string[]>([]);

  // eBay accounts overview
  type EbayAccountWithToken = {
    id: string;
    org_id: string;
    ebay_user_id: string;
    username: string | null;
    house_name: string;
    purpose: string;
    marketplace_id?: string | null;
    site_id?: number | null;
    connected_at: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
    token?: {
      id: string;
      ebay_account_id: string;
      expires_at?: string | null;
      last_refreshed_at?: string | null;
      refresh_error?: string | null;
    } | null;
    status: string;
    expires_in_seconds?: number | null;
    last_health_check?: string | null;
    health_status?: string | null;
  };
  const [accounts, setAccounts] = useState<EbayAccountWithToken[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState('');
  const [selectedConnectAccountId, setSelectedConnectAccountId] = useState<string | null>(null);

  // Account detail modal state (token + scopes)
  const [accountDetailOpen, setAccountDetailOpen] = useState(false);
  const [accountDetailLoading, setAccountDetailLoading] = useState(false);
  const [accountDetailError, setAccountDetailError] = useState('');
  const [selectedAccount, setSelectedAccount] = useState<EbayAccountWithToken | null>(null);
  const [accountScopes, setAccountScopes] = useState<string[]>([]);
  const [accountTokenInfo, setAccountTokenInfo] = useState<any | null>(null);

  // Pre-flight modal state
  const [preflightOpen, setPreflightOpen] = useState(false);
  const [preflightUrl, setPreflightUrl] = useState<string>('');
  const [preflightScopes, setPreflightScopes] = useState<string[]>([]);
  const [extraScopesInput, setExtraScopesInput] = useState<string>('');
  const [preflightSubmitting, setPreflightSubmitting] = useState(false);

  // Compact: collapse Connection Request Preview details by default
  const [showRequestPreview, setShowRequestPreview] = useState(false);

  useEffect(() => {
    if (user?.role !== 'admin') {
      navigate('/dashboard');
      return;
    }
    loadConnectionStatus();
    loadLogs();
    loadAvailableScopes();
    loadAccounts();
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

  const loadAvailableScopes = async () => {
    try {
      const res = await ebayApi.getAvailableScopes();
      const scopes = (res.scopes || []).map((s) => s.scope);
      setAvailableScopes(scopes);
    } catch (err) {
      console.error('Failed to load available eBay scopes:', err);
    }
  };

  const loadAccounts = async () => {
    try {
      setAccountsLoading(true);
      setAccountsError('');
      const data = await ebayApi.getAccounts(true);
      setAccounts(data || []);
      if (!selectedConnectAccountId && data && data.length > 0) {
        setSelectedConnectAccountId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load eBay accounts:', err);
      setAccountsError('Failed to load eBay accounts');
    } finally {
      setAccountsLoading(false);
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
      // For now always initiate auth in production
      const env: 'sandbox' | 'production' = 'production';
      localStorage.setItem('ebay_oauth_environment', env);

      const selectedAcc = accounts.find((a) => a.id === selectedConnectAccountId) || null;
      const houseName = selectedAcc?.house_name || selectedAcc?.username || undefined;

      const response = await ebayApi.startAuth(redirectUri, env, undefined, houseName);
      setPreflightUrl(response.authorization_url);
      // Parse scopes from URL for display
      try {
        const u = new URL(response.authorization_url);
        const scopeStr = (u.searchParams.get('scope') || '').trim();
        setPreflightScopes(scopeStr ? scopeStr.split(' ') : []);
      } catch {}
      setPreflightOpen(true);
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

  const getAccountStatusDot = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500';
      case 'expiring_soon':
        return 'bg-yellow-400';
      case 'expired':
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-400';
    }
  };

  const maskToken = (token: string | undefined | null) => {
    if (!token) return '';
    if (token.length <= 12) return token;
    return `${token.slice(0, 6)}…${token.slice(-4)}`;
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString(undefined, { hour12: false });
    } catch {
      return timestamp;
    }
  };

  const openAccountDetail = async (acc: EbayAccountWithToken) => {
    setSelectedAccount(acc);
    setAccountDetailOpen(true);
    setAccountDetailLoading(true);
    setAccountDetailError('');
    setAccountScopes([]);
    setAccountTokenInfo(null);
    try {
      // Load scopes for this account
      const authRes = await api.get(`/ebay-accounts/${acc.id}/authorizations`);
      const scopes: string[] = Array.from(
        new Set(
          (authRes.data || []).flatMap((a: any) => Array.isArray(a.scopes) ? a.scopes : []),
        ),
      );
      setAccountScopes(scopes);
    } catch (e: any) {
      setAccountDetailError(e?.response?.data?.detail || 'Failed to load account scopes');
    }

    try {
      // Load token info (masked token, expiry, etc.)
      const params = new URLSearchParams({ environment });
      params.set('account_id', acc.id);
      const tokenRes = await api.get(`/ebay/token-info?${params.toString()}`);
      setAccountTokenInfo(tokenRes.data);
    } catch (e: any) {
      // Do not block modal if token-info fails; surface message if nothing else loaded
      if (!accountDetailError) {
        setAccountDetailError(e?.response?.data?.detail || 'Failed to load token info');
      }
    } finally {
      setAccountDetailLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-16 px-4 sm:px-6 lg:px-10 py-8">
        <div className="w-full mx-auto">
          <h1 className="text-4xl font-bold mb-8 tracking-tight">eBay Connection Management</h1>

          <Tabs defaultValue="connection" className="space-y-4">
              <TabsList className="flex flex-wrap gap-2 bg-white rounded-lg shadow-sm px-2 py-1">
              <TabsTrigger value="connection" className="text-sm px-3 py-1">eBay Connection</TabsTrigger>
              <TabsTrigger value="accounts" className="text-sm px-3 py-1">eBay Accounts</TabsTrigger>
              <TabsTrigger value="sync" className="text-sm px-3 py-1">Sync Data</TabsTrigger>
              <TabsTrigger value="debugger" className="text-sm px-3 py-1">🔧 API Debugger</TabsTrigger>
              <TabsTrigger value="terminal" className="text-sm px-3 py-1">Connection Terminal</TabsTrigger>
            </TabsList>

            <TabsContent value="connection" className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <Card>
                <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <CardTitle className="text-xl">eBay Connection</CardTitle>
                    <CardDescription className="text-sm text-gray-600">
                      Select an eBay account and start a new OAuth connect flow.
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
                    <Badge variant="destructive">Production (Live)</Badge>
                    {connectionStatus?.connected && (
                      <>
                        <Badge className="bg-green-100 text-green-800 flex items-center gap-1">
                          <LinkIcon className="w-3 h-3" />
                          Connected
                        </Badge>
                        {connectionStatus.expires_at && (
                          <span className="text-gray-600">
                            Expires: {new Date(connectionStatus.expires_at).toLocaleString()}
                          </span>
                        )}
                        <Button 
                          onClick={() => navigate('/ebay/test')}
                          disabled={loading}
                          size="sm"
                        >
                          Test API
                        </Button>
                        <Button 
                          variant="destructive" 
                          onClick={handleDisconnect}
                          disabled={loading}
                          size="sm"
                        >
                          {loading ? 'Disconnecting…' : 'Disconnect'}
                        </Button>
                      </>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    <div className="flex-1">
                      <Label className="text-xs font-medium text-gray-700">eBay account to (re)connect</Label>
                      {accountsLoading ? (
                        <div className="text-xs text-gray-500 mt-1">Loading accounts…</div>
                      ) : accounts.length > 0 ? (
                        <Select
                          value={selectedConnectAccountId || accounts[0]?.id}
                          onValueChange={(val) => setSelectedConnectAccountId(val)}
                        >
                          <SelectTrigger className="mt-1 h-8 text-xs w-full sm:w-72">
                            <SelectValue placeholder="Select eBay account" />
                          </SelectTrigger>
                          <SelectContent>
                            {accounts.map((acc) => (
                              <SelectItem key={acc.id} value={acc.id}>
                                {acc.house_name || acc.username || acc.id} ({acc.ebay_user_id})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <p className="text-xs text-gray-500 mt-1">
                          No eBay accounts yet. Connecting will create a new account from the eBay user you log in with.
                        </p>
                      )}
                    </div>
                    <div className="flex items-end sm:items-center gap-2">
                      <Button 
                        onClick={handleConnectEbay}
                        disabled={loading || (accounts.length > 0 && !selectedConnectAccountId)}
                        size="sm"
                      >
                        {loading ? 'Connecting…' : 'Connect to eBay'}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="text-xl">Connection Request Preview</CardTitle>
                    <CardDescription className="text-sm text-gray-600">
                      Preview of the authorization request that will be sent to eBay for the selected environment.
                    </CardDescription>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs"
                    onClick={() => setShowRequestPreview((v) => !v)}
                  >
                    {showRequestPreview ? 'Hide details' : 'Show details'}
                  </Button>
                </CardHeader>
                {showRequestPreview && (
                <CardContent className="pt-2">
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
                    <div className="mt-3">
                      <h4 className="text-sm font-semibold mb-2">Query Parameters</h4>
                      <ScrollArea className="h-24 rounded border bg-gray-50 p-3 text-xs font-mono">
                      {Array.from(
                        new URLSearchParams({
                          response_type: 'code',
                          redirect_uri: typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback',
                          scope: (availableScopes.length ? availableScopes : DEFAULT_SCOPES).join(' '),
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
                      <div className="p-2 bg-gray-50 border rounded font-mono text-xs whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
                        {(() => {
                          const base = environment === 'production' ? 'https://auth.ebay.com/oauth2/authorize' : 'https://auth.sandbox.ebay.com/oauth2/authorize';
                          const qs = new URLSearchParams({
                            response_type: 'code',
                            redirect_uri: typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback',
                            scope: (availableScopes.length ? availableScopes : DEFAULT_SCOPES).join(' '),
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
                )}
              </Card>

              {/* Pre-flight Authorization Modal */}
              <Dialog open={preflightOpen} onOpenChange={(o)=> { setPreflightOpen(o); if (!o) { setLoading(false); setPreflightSubmitting(false); } }}>
                <DialogContent className="max-w-3xl max-h-[70vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>Review eBay Authorization Request</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 text-sm">
                    <div className="p-3 bg-gray-50 rounded border font-mono text-xs overflow-x-auto whitespace-pre-wrap break-words">
                      GET {preflightUrl}
                    </div>
                    <div>
                      <div className="font-semibold mb-1">Scopes from URL</div>
                      {preflightScopes.length > 0 ? (
                        <div className="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
                          {preflightScopes.map((s,i)=> (
                            <span key={i} className="text-xs px-2 py-0.5 border rounded bg-gray-50 break-all">{s}</span>
                          ))}
                        </div>
                      ) : (
                        <div className="text-gray-600">(none parsed)</div>
                      )}
                    </div>
                    <div>
                      <div className="font-semibold mb-1">Additional scopes (space-separated)</div>
                      <textarea
                        className="w-full border rounded p-2 font-mono text-xs"
                        rows={3}
                        placeholder="Paste extra scopes here to request all whitelisted ones"
                        value={extraScopesInput}
                        onChange={(e)=> setExtraScopesInput(e.target.value)}
                      />
                      <div className="text-xs text-gray-500 mt-1">We’ll merge these with the current list and request them in one authorization.</div>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={()=> { setPreflightOpen(false); setLoading(false); setPreflightSubmitting(false); }}>Cancel</Button>
                    <Button
                      variant="outline"
                      disabled={preflightSubmitting}
                      onClick={async ()=> {
                        try {
                          setPreflightSubmitting(true);
                          const redirectUri = `${window.location.origin}/ebay/callback`;
                          const baseScopes = (availableScopes.length ? availableScopes : DEFAULT_SCOPES);
                          const union = Array.from(new Set(baseScopes));
                          const { data } = await api.post(
                            `/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`,
                            { scopes: union },
                          );
                          setPreflightOpen(false);
                          window.location.assign(data.authorization_url);
                        } catch (e) {
                          setLoading(false);
                          setPreflightSubmitting(false);
                        }
                      }}
                    >
                      Request all my scopes
                    </Button>
                    <Button
                      disabled={preflightSubmitting}
                      onClick={async ()=> {
                        try {
                          setPreflightSubmitting(true);
                          const redirectUri = `${window.location.origin}/ebay/callback`;
                          const baseScopes = (availableScopes.length ? availableScopes : DEFAULT_SCOPES);
                          const added = (extraScopesInput||'').trim().split(/\s+/).filter(Boolean);
                          const union = added.length > 0
                            ? Array.from(new Set([...baseScopes, ...added]))
                            : Array.from(new Set(baseScopes));
                          const { data } = await api.post(
                            `/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`,
                            { scopes: union },
                          );
                          setPreflightOpen(false);
                          window.location.assign(data.authorization_url);
                        } catch (e) {
                          setLoading(false);
                          setPreflightSubmitting(false);
                        }
                      }}
                    >
                      {preflightSubmitting ? 'Redirecting…' : 'Proceed to eBay'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

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
                        <Input
                          placeholder="Search logs"
                          value={connectSearch}
                          onChange={(e) => setConnectSearch(e.target.value)}
                          className="h-8 w-40 text-xs bg-gray-800 text-gray-100 border-gray-700 mr-2"
                        />
                        <Button size="sm" variant="outline" onClick={() => exportConnectLogs('json')}>Save JSON</Button>
                      <Button size="sm" variant="outline" onClick={() => exportConnectLogs('ndjson')}>Save NDJSON</Button>
                      <Button size="sm" variant="outline" onClick={() => exportConnectLogs('txt')}>Save TXT</Button>
                      <Button size="sm" variant="outline" onClick={() => setConnWrap(w => !w)}>{connWrap ? 'Disable wrap' : 'Wrap lines'}</Button>
                    </div>
                  </div>
                  {connectLogLoading && (
                    <div className="flex items-center text-sm text-gray-600 mb-2">
                      <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading connection logs...
                    </div>
                  )}
                  <div className="min-h-[60vh] max-h-[80vh] rounded border bg-gray-950 p-4 text-sm font-mono overflow-auto">
                    {connectLogs.length === 0 ? (
                      <div className="text-gray-400">
                        No connection events yet. Click "Connect to eBay" to generate logs.
                      </div>
                    ) : (
                      connectLogs
                        .filter((log) => {
                          if (!connectSearch.trim()) return true;
                          const q = connectSearch.toLowerCase();
                          try {
                            return JSON.stringify(log).toLowerCase().includes(q);
                          } catch {
                            return false;
                          }
                        })
                        .map((log) => (
                        <div key={log.id} className="border-b border-gray-800 pb-4 mb-4 last:border-0 last:pb-0 last:mb-0 text-white">
                          <div className="flex flex-wrap items-center justify-between text-gray-400">
                            <span>[{new Date(log.created_at).toLocaleString()}]</span>
                            <span>{log.environment === 'sandbox' ? '🧪 Sandbox' : '🚀 Production'} • {log.action}</span>
                          </div>
                          {log.request && (
                            <div className="mt-2">
                              <div className="text-green-400 font-semibold">→ REQUEST</div>
                              <pre className={`mt-1 text-green-200 ${connWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                                {`${log.request.method || ''} ${log.request.url || ''}`}
                              </pre>
                              {log.request.headers && (
                                <pre className={`mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-32 text-green-100 ${connWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'}`}>{JSON.stringify(log.request.headers, null, 2)}</pre>
                              )}
                              {log.request.body && (
                                <pre className={`mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-32 text-green-100 ${connWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'}`}>{typeof log.request.body === 'string' ? log.request.body : JSON.stringify(log.request.body, null, 2)}</pre>
                              )}
                            </div>
                          )}
                          {log.response && (
                            <div className="mt-2">
                              <div className={`font-semibold ${log.response.status && log.response.status >= 200 && log.response.status < 300 ? 'text-blue-300' : 'text-red-300'}`}>
                                ← RESPONSE {log.response.status ?? ''}
                              </div>
                              {log.response.headers && (
                                <pre className={`mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-32 text-blue-100 ${connWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'}`}>{JSON.stringify(log.response.headers, null, 2)}</pre>
                              )}
                              {typeof log.response.body !== 'undefined' && (
                                <pre className={`mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-48 text-blue-100 ${connWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'}`}>{typeof log.response.body === 'string' ? log.response.body : JSON.stringify(log.response.body, null, 2)}</pre>
                              )}
                            </div>
                          )}
                          {log.error && (
                            <div className="mt-2 text-red-400">⚠️ {log.error}</div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="accounts" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">eBay Accounts</CardTitle>
                  <CardDescription className="text-sm text-gray-600">
                    All eBay accounts for this organization, with token status and health.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {accountsLoading && (
                    <div className="text-sm text-gray-600">Loading accounts...</div>
                  )}
                  {accountsError && (
                    <Alert variant="destructive" className="mb-2">
                      <AlertDescription>{accountsError}</AlertDescription>
                    </Alert>
                  )}
                  {!accountsLoading && !accountsError && accounts.length === 0 && (
                    <div className="text-sm text-gray-600">No eBay accounts found. Connect to eBay to create an account.</div>
                  )}
                  {accounts.length > 0 && (
                    <div className="space-y-3">
                      {accounts.map((acc) => (
                        <button
                          key={acc.id}
                          type="button"
                          onClick={() => openAccountDetail(acc)}
                          className="w-full text-left border rounded p-3 bg-gray-50 flex flex-col gap-2 text-sm hover:bg-white hover:border-blue-300 transition cursor-pointer"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-gray-900">
                                  {acc.house_name || acc.username || acc.id}
                                </span>
                                <span className={`inline-flex h-2 w-2 rounded-full ${getAccountStatusDot(acc.status)}`} />
                                <span className="text-xs uppercase tracking-wide text-gray-500">
                                  {acc.status}
                                </span>
                              </div>
                              <div className="text-xs text-gray-600">
                                eBay: {acc.username || '—'} ({acc.ebay_user_id})
                              </div>
                              <div className="text-xs text-gray-500">
                                Connected at: {new Date(acc.connected_at).toLocaleString()}
                              </div>
                            </div>
                            <div className="flex flex-col items-end gap-1 text-xs text-gray-600">
                              {typeof acc.expires_in_seconds === 'number' && (
                                <div>TTL: {acc.expires_in_seconds}s</div>
                              )}
                              {acc.token?.expires_at && (
                                <div>Expires: {new Date(acc.token.expires_at).toLocaleString()}</div>
                              )}
                              {acc.last_health_check && (
                                <div>Last health: {new Date(acc.last_health_check).toLocaleString()}</div>
                              )}
                              {acc.token?.refresh_error && (
                                <div className="text-red-500">Last error: {acc.token.refresh_error}</div>
                              )}
                            </div>
                          </div>
                          <div className="mt-1 text-xs text-blue-600 flex items-center gap-1">
                            <span>View token details &amp; scopes</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Account detail modal */}
              <Dialog open={accountDetailOpen} onOpenChange={(open) => {
                setAccountDetailOpen(open);
                if (!open) {
                  setSelectedAccount(null);
                  setAccountScopes([]);
                  setAccountTokenInfo(null);
                  setAccountDetailError('');
                }
              }}>
                <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>
                      {selectedAccount ? (selectedAccount.house_name || selectedAccount.username || selectedAccount.id) : 'eBay Account'}
                    </DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 text-sm">
                    {selectedAccount && (
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex h-2 w-2 rounded-full ${getAccountStatusDot(selectedAccount.status)}`} />
                            <span className="text-xs uppercase tracking-wide text-gray-600">{selectedAccount.status}</span>
                          </div>
                          <div className="text-xs text-gray-600">
                            eBay: {selectedAccount.username || '—'} ({selectedAccount.ebay_user_id})
                          </div>
                          <div className="text-xs text-gray-500">
                            Connected at: {new Date(selectedAccount.connected_at).toLocaleString()}
                          </div>
                        </div>
                        <div className="text-xs text-gray-600 space-y-1 text-right">
                          {selectedAccount.token?.expires_at && (
                            <div>Access expires: {new Date(selectedAccount.token.expires_at).toLocaleString()}</div>
                          )}
                          {selectedAccount.token?.last_refreshed_at && (
                            <div>Last refresh: {new Date(selectedAccount.token.last_refreshed_at).toLocaleString()}</div>
                          )}
                        </div>
                      </div>
                    )}

                    {accountDetailLoading && (
                      <div className="flex items-center gap-2 text-xs text-gray-600">
                        <Loader2 className="h-4 w-4 animate-spin" /> Loading token details...
                      </div>
                    )}

                    {accountDetailError && (
                      <Alert variant="destructive">
                        <AlertDescription className="text-xs">{accountDetailError}</AlertDescription>
                      </Alert>
                    )}

                    {accountTokenInfo && (
                      <div className="space-y-2">
                        <h3 className="text-sm font-semibold">Token</h3>
                        <div className="bg-gray-50 border rounded p-2 text-xs font-mono space-y-1">
                          <div>Access token: {maskToken(accountTokenInfo.token_full)}</div>
                          <div>Expires at: {accountTokenInfo.token_expires_at || 'unknown'}</div>
                          <div>Scopes count: {accountTokenInfo.scopes_count}</div>
                        </div>
                      </div>
                    )}

                    {accountScopes.length > 0 && (
                      <div className="space-y-2">
                        <h3 className="text-sm font-semibold">Scopes</h3>
                        <div className="flex flex-wrap gap-1 max-h-48 overflow-y-auto">
                          {accountScopes.map((s) => (
                            <span key={s} className="text-[11px] px-2 py-0.5 border rounded bg-gray-50 break-all">
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {accountScopes.length === 0 && !accountDetailLoading && !accountDetailError && (
                      <div className="text-xs text-gray-500">No scopes recorded yet for this account.</div>
                    )}
                  </div>
                  <DialogFooter>
                    <Button variant="outline" size="sm" onClick={() => setAccountDetailOpen(false)}>
                      Close
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

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
                  <div className="flex items-center gap-2">
                    <Input
                      placeholder="Search logs"
                      value={terminalSearch}
                      onChange={(e) => setTerminalSearch(e.target.value)}
                      className="h-8 w-40 text-xs bg-gray-800 text-gray-100 border-gray-700"
                    />
                    <Button variant="outline" size="sm" onClick={handleClearLogs}>
                      Clear Logs
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="min-h-[60vh] max-h-[80vh] w-full rounded-md border bg-black text-white p-4 font-mono text-sm overflow-x-auto">
                    {logs.length === 0 ? (
                      <div className="text-gray-400">No logs yet. Connect to eBay to see credential exchanges.</div>
                    ) : (
                      <div className="space-y-2">
                        {logs
                          .filter((log) => {
                            if (!terminalSearch.trim()) return true;
                            const q = terminalSearch.toLowerCase();
                            try {
                              return JSON.stringify(log).toLowerCase().includes(q);
                            } catch {
                              return false;
                            }
                          })
                          .map((log, index) => (
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
