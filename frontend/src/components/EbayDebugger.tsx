import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Textarea } from './ui/textarea';
import { Alert, AlertDescription } from './ui/alert';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Switch } from './ui/switch';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import api from '../lib/apiClient';
import { ebayApi } from '../api/ebay';
// Feature flag with safe fallbacks: env var, localStorage, or ?tokeninfo=1
const FEATURE_TOKEN_INFO = (
  (import.meta.env.VITE_FEATURE_TOKEN_INFO === 'true') ||
  (typeof window !== 'undefined' && (localStorage.getItem('enable_token_info') === '1' || new URLSearchParams(window.location.search).get('tokeninfo') === '1'))
);

// Full set of whitelisted scopes provided by admin (base first)
const MY_SCOPES: string[] = [
  'https://api.ebay.com/oauth/api_scope',
  'https://api.ebay.com/oauth/api_scope/sell.marketing.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.marketing',
  'https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.inventory',
  'https://api.ebay.com/oauth/api_scope/sell.account.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.account',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
  'https://api.ebay.com/oauth/api_scope/sell.analytics.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.finances',
  'https://api.ebay.com/oauth/api_scope/sell.payment.dispute',
  'https://api.ebay.com/oauth/api_scope/commerce.identity.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.reputation',
  'https://api.ebay.com/oauth/api_scope/sell.reputation.readonly',
  'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription',
  'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.stores',
  'https://api.ebay.com/oauth/api_scope/sell.stores.readonly',
  'https://api.ebay.com/oauth/scope/sell.edelivery',
  'https://api.ebay.com/oauth/api_scope/commerce.vero',
  'https://api.ebay.com/oauth/api_scope/sell.inventory.mapping',
  'https://api.ebay.com/oauth/api_scope/commerce.message',
  'https://api.ebay.com/oauth/api_scope/commerce.feedback',
  'https://api.ebay.com/oauth/api_scope/commerce.shipping',
];
import { Loader2, Play, Copy, Check } from 'lucide-react';

interface DebugTemplate {
  name: string;
  description: string;
  method: string;
  path: string;
  params: Record<string, string>;
}

interface RequestContext {
  user_email: string;
  user_id: string;
  token: string;
  token_masked?: string;
  token_full?: string;
  token_version?: string;
  token_expires_at?: string;
  scopes: string[];
  scopes_display: string;
  scopes_full?: string[];
  environment: string;
  missing_scopes: string[];
  has_all_required?: boolean;
}

interface DebugResponse {
  request_context?: RequestContext;
  request: {
    method: string;
    url: string;
    url_full?: string;
    headers: Record<string, string>;
    headers_full?: Record<string, string>;
    params: Record<string, string>;
    body?: string;
    curl_command?: string;
  };
  response: {
    status_code: number;
    status_text: string;
    headers: Record<string, string>;
    ebay_headers: Record<string, string>;
    body: any;
    response_time_ms: number;
  };
  success: boolean;
}

interface TokenInfo {
  user_email: string;
  user_id: string;
  ebay_environment: string;
  token_full: string;
  token_length: number;
  token_version?: string;
  token_expires_at?: string;
  scopes: string[];
  scopes_display: string;
  scopes_count: number;
  ebay_connected: boolean;
  ebay_user_id?: string;
  ebay_username?: string;
}

export const EbayDebugger: React.FC = () => {
  const [templates, setTemplates] = useState<Record<string, DebugTemplate>>({});
  const [selectedTemplate, setSelectedTemplate] = useState<string>('custom');
  const [method, setMethod] = useState<string>('GET');
  const [path, setPath] = useState<string>('');
  const [params, setParams] = useState<string>('');
  const [headers, setHeaders] = useState<string>('');
  const [body, setBody] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<DebugResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [stdError, setStdError] = useState<string>('');
  const [rawError, setRawError] = useState<string>('');
  
  // Total Testing Mode
  const [totalTestingMode, setTotalTestingMode] = useState(false);
  const [debugLogs, setDebugLogs] = useState<any[]>([]);
  const [debugLogsLoading, setDebugLogsLoading] = useState(false);
  const [rawRequest, setRawRequest] = useState<string>('');
  const [copied, setCopied] = useState<string>('');
  const [lineWrap, setLineWrap] = useState<boolean>(false);

  // Reconnect modal state
  const [showReconnect, setShowReconnect] = useState(false);
  const [reconnectUrl, setReconnectUrl] = useState('');
  const [reconnectScopes, setReconnectScopes] = useState<string[]>([]);
  
  // Token Info
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null);
  const [adminTokenInfo, setAdminTokenInfo] = useState<any | null>(null);
  const [refreshingAdmin, setRefreshingAdmin] = useState(false);
  const [tokenInfoLoading, setTokenInfoLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'debugger' | 'token-info'>('debugger');

  // eBay accounts for account selection (multi-account)
  type EbayAccountWithToken = {
    id: string;
    org_id: string;
    ebay_user_id: string;
    username: string | null;
    house_name: string;
    status: string;
    token?: {
      id: string;
      ebay_account_id: string;
      expires_at?: string | null;
      last_refreshed_at?: string | null;
      refresh_error?: string | null;
    } | null;
  };
  const [accounts, setAccounts] = useState<EbayAccountWithToken[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  // Admin view: accounts + scopes vs catalog
  type AdminAccountsScopes = {
    scope_catalog: { scope: string; grant_type: string; description?: string }[];
    accounts: {
      id: string;
      username: string | null;
      ebay_user_id: string;
      house_name: string;
      is_active: boolean;
      connected_at?: string | null;
      scopes: string[];
      scopes_count: number;
      has_all_catalog_scopes: boolean;
      missing_catalog_scopes: string[];
      token?: { access_expires_at?: string | null; has_refresh_token?: boolean } | null;
    }[];
  } | null;
  const [accountsScopes, setAccountsScopes] = useState<AdminAccountsScopes>(null);
  const [accountsScopesLoading, setAccountsScopesLoading] = useState(false);
  const [accountsScopesError, setAccountsScopesError] = useState<string | null>(null);
  const [environment, setEnvironment] = useState<'sandbox' | 'production'>(() => {
    const saved = localStorage.getItem('ebay_environment');
    return (saved === 'production' ? 'production' : 'sandbox') as 'sandbox' | 'production';
  });
  
  // Admin Token Terminal (persistent logs from backend)
  type TokenLogEntry = {
    id: string;
    environment: string;
    action: string;
    request?: { method?: string; url?: string };
    response?: { status?: number; body?: any };
    error?: string;
    created_at: string;
  };
  const [tokenLogs, setTokenLogs] = useState<TokenLogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  // Token Info API Request/Response History (local preview of identity calls)
  type TokenInfoHistoryEntry = {
    timestamp: string;
    environment: string;
    request: {
      method: string;
      url: string;
      headers: Record<string, string>;
    };
    response: {
      status: number;
      headers: Record<string, string>;
      body: any;
      ebay_headers?: Record<string, string>;
    };
  };
  const [tokenInfoHistory, setTokenInfoHistory] = useState<TokenInfoHistoryEntry[]>([]);
  const [tokenInfoRequestLoading, setTokenInfoRequestLoading] = useState(false);

  useEffect(() => {
    loadTemplates();
    void loadAccounts();
    if (activeTab === 'debugger') {
      // Keep debugger terminal fresh, but keep controls compact
      void loadDebuggerLogs();
      // Also load lightweight token info for the selected account (no Identity call)
      void loadTokenInfo(environment, { skipIdentityTest: true });
      const id = setInterval(() => { if (!totalTestingMode) void loadDebuggerLogs(); }, 10000);
      return () => clearInterval(id);
    }
    if (activeTab === 'token-info') {
      loadTokenInfo();
      if (FEATURE_TOKEN_INFO && environment === 'production') {
        void loadAdminTokenInfo();
        void loadTokenLogs();
        void loadAdminAccountsScopes();
      }
    }
  }, [activeTab, environment, totalTestingMode]);

  // Reset errors when switching mode
  useEffect(() => {
    setStdError('');
    setRawError('');
  }, [totalTestingMode]);

  // Update rawRequest URL when environment changes
  useEffect(() => {
    if (totalTestingMode && rawRequest) {
      const apiBaseUrl = environment === 'sandbox' 
        ? 'https://api.sandbox.ebay.com' 
        : 'https://api.ebay.com';
      
      // Replace URL in rawRequest if it contains eBay API URL
      const updatedRequest = rawRequest.replace(
        /https:\/\/api\.(sandbox\.)?ebay\.com/g,
        apiBaseUrl
      );
      
      if (updatedRequest !== rawRequest) {
        setRawRequest(updatedRequest);
      }
    }
  }, [environment, totalTestingMode]);

  // When reconnect modal opens or scopes change, pre-generate the authorization URL.
  // IMPORTANT: always request the full whitelisted scope set, not just the minimal missing scopes,
  // so that reconnect from the Debugger never "shrinks" the token to a narrower scope set.
  useEffect(() => {
    const gen = async () => {
      if (!showReconnect || reconnectScopes.length === 0) return;
      try {
        const redirectUri = `${window.location.origin}/ebay/callback`;
        const union = Array.from(new Set([...(reconnectScopes || []), ...MY_SCOPES]));
        const { data } = await api.post(
          `/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`,
          { scopes: union },
        );
        setReconnectUrl(data.authorization_url);
      } catch {
        // ignore
      }
    };
    void gen();
  }, [showReconnect, reconnectScopes, environment]);

  const loadAccounts = async () => {
    try {
      setAccountsLoading(true);
      setAccountsError(null);
      const data = await ebayApi.getAccounts(true);
      setAccounts(data || []);
      if (!selectedAccountId && data && data.length > 0) {
        setSelectedAccountId(data[0].id);
      }
    } catch (e: any) {
      console.error('Failed to load eBay accounts:', e);
      setAccountsError(e?.response?.data?.detail || 'Failed to load eBay accounts');
    } finally {
      setAccountsLoading(false);
    }
  };

  const loadAdminTokenInfo = async () => {
    if (environment !== 'production') { setAdminTokenInfo(null); return; }
    try {
      const { data } = await api.get('/admin/ebay/tokens/info?env=production');
      setAdminTokenInfo(data);
    } catch (e:any) {
      setAdminTokenInfo({ error: e?.response?.data?.detail || 'failed_to_load' });
    }
  };

  const loadTokenLogs = async () => {
    if (!FEATURE_TOKEN_INFO || environment !== 'production') { setTokenLogs([]); return; }
    setLogsLoading(true);
    try {
      const { data } = await api.get('/admin/ebay/tokens/logs?env=production&limit=100');
      setTokenLogs(data?.logs || []);
    } catch (e) {
      // ignore
    } finally {
      setLogsLoading(false);
    }
  };

  // Auto-poll logs every 10s while on token-info tab in production
  useEffect(() => {
    if (!(environment === 'production' && activeTab === 'token-info')) return;
    const id = setInterval(() => { void loadTokenLogs(); }, 10000);
    return () => clearInterval(id);
  }, [FEATURE_TOKEN_INFO, environment, activeTab]);

  const refreshAdminToken = async () => {
    if (environment !== 'production') return;
    setRefreshingAdmin(true);
    try {
      await api.post('/admin/ebay/tokens/refresh?env=production');
      await loadAdminTokenInfo();
      await loadTokenLogs();
      await loadAdminAccountsScopes();
    } finally {
      setRefreshingAdmin(false);
    }
  };

  const loadAdminAccountsScopes = async () => {
    if (!FEATURE_TOKEN_INFO || environment !== 'production') {
      setAccountsScopes(null);
      setAccountsScopesError(null);
      return;
    }
    setAccountsScopesLoading(true);
    setAccountsScopesError(null);
    try {
      const { data } = await api.get('/admin/ebay/accounts/scopes');
      setAccountsScopes(data);
    } catch (e: any) {
      setAccountsScopesError(e?.response?.data?.detail || 'Failed to load accounts/scopes');
    } finally {
      setAccountsScopesLoading(false);
    }
  };

  const loadTokenInfo = async (
    env?: 'sandbox' | 'production',
    options?: { skipIdentityTest?: boolean },
  ) => {
    const targetEnv = env || environment;
    setTokenInfoLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ environment: targetEnv });
      if (selectedAccountId) params.set('account_id', selectedAccountId);
      const res = await api.get(`/ebay/token-info?${params.toString()}`);
      setTokenInfo(res.data);
      
      // Automatically test Identity API call if token is available (unless explicitly skipped)
      if (res.data.token_full && res.data.ebay_connected && !options?.skipIdentityTest) {
        await testIdentityAPI(targetEnv, res.data.token_full);
      }
    } catch (err: any) {
      console.error('Failed to load token info:', err);
      setError(err.response?.data?.detail || 'Failed to load token info');
    } finally {
      setTokenInfoLoading(false);
    }
  };

  const handleEnvironmentChange = (newEnv: 'sandbox' | 'production') => {
    if (environment === newEnv) return;
    setEnvironment(newEnv);
    localStorage.setItem('ebay_environment', newEnv);
    setError('');
    if (activeTab === 'token-info') {
      void loadTokenInfo(newEnv);
    } else if (activeTab === 'debugger') {
      // Keep small token badge in sync without spamming Identity API
      void loadTokenInfo(newEnv, { skipIdentityTest: true });
    }
  };

  const testIdentityAPI = async (env: 'sandbox' | 'production', token: string) => {
    setTokenInfoRequestLoading(true);
    const timestamp = new Date().toISOString();
    const apiBaseUrl = env === 'sandbox' 
      ? 'https://api.sandbox.ebay.com' 
      : 'https://api.ebay.com';
    const url = `${apiBaseUrl}/identity/v1/oauth2/userinfo`;
    
    const request = {
      method: 'GET',
      url: url,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'
      }
    };

    try {
      // Make actual API call through our debug endpoint
      const queryParams = new URLSearchParams({
        method: 'GET',
        path: '/identity/v1/oauth2/userinfo',
        environment: env
      });
      if (selectedAccountId) {
        queryParams.set('account_id', selectedAccountId);
      }
      const res = await api.post(`/ebay/debug?${queryParams.toString()}`, {});
      
      const historyEntry: TokenInfoHistoryEntry = {
        timestamp,
        environment: env,
        request,
        response: {
          status: res.data.response.status_code,
          headers: res.data.response.headers,
          body: res.data.response.body,
          ebay_headers: res.data.response.ebay_headers || {}
        }
      };
      
      // Add to history
      const newHistory = [historyEntry, ...tokenInfoHistory].slice(0, 50); // Keep last 50
      setTokenInfoHistory(newHistory);
      
      // Save to localStorage
      try {
        const savedHistory = JSON.parse(localStorage.getItem('token_info_history') || '[]');
        const updatedHistory = [historyEntry, ...savedHistory].slice(0, 50);
        localStorage.setItem('token_info_history', JSON.stringify(updatedHistory));
      } catch (e) {
        console.error('Failed to save history to localStorage:', e);
      }
      
    } catch (err: any) {
      const historyEntry: TokenInfoHistoryEntry = {
        timestamp,
        environment: env,
        request,
        response: {
          status: err.response?.status || 0,
          headers: err.response?.headers || {},
          body: err.response?.data || { error: err.message }
        }
      };
      
      const newHistory = [historyEntry, ...tokenInfoHistory].slice(0, 50);
      setTokenInfoHistory(newHistory);
      
      try {
        const savedHistory = JSON.parse(localStorage.getItem('token_info_history') || '[]');
        const updatedHistory = [historyEntry, ...savedHistory].slice(0, 50);
        localStorage.setItem('token_info_history', JSON.stringify(updatedHistory));
      } catch (e) {
        console.error('Failed to save history to localStorage:', e);
      }
    } finally {
      setTokenInfoRequestLoading(false);
    }
  };

  // Load history from localStorage on mount
  useEffect(() => {
    try {
      const savedHistory = JSON.parse(localStorage.getItem('token_info_history') || '[]');
      setTokenInfoHistory(savedHistory.slice(0, 50));
    } catch (e) {
      console.error('Failed to load history from localStorage:', e);
    }
  }, []);

  const loadTemplates = async () => {
    try {
      const res = await api.get('/ebay/debug/templates');
      setTemplates(res.data.templates || {});
    } catch (err: any) {
      console.error('Failed to load templates:', err);
      setError(err.response?.data?.detail || 'Failed to load templates');
    }
  };

  const REQUIRED_SCOPES_BY_TEMPLATE: Record<string, string[]> = {
    identity: ['https://api.ebay.com/oauth/api_scope'],
    orders: ['https://api.ebay.com/oauth/api_scope/sell.fulfillment'],
    transactions: ['https://api.ebay.com/oauth/api_scope/sell.finances'],
    inventory: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
    offers: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
    disputes: ['https://api.ebay.com/oauth/api_scope/sell.fulfillment'],
    messages: ['https://api.ebay.com/oauth/api_scope/trading'],
  };

  const loadDebuggerLogs = async () => {
    try {
      setDebugLogsLoading(true);
      const { data } = await api.get(`/ebay/connect/logs?environment=${environment}&limit=100`);
      const onlyDebug = (data.logs || []).filter((l:any)=> String(l.action||'').startsWith('debug_'));
      setDebugLogs(onlyDebug);
    } catch {
      // ignore
    } finally {
      setDebugLogsLoading(false);
    }
  };

  // Export helpers for debugger terminal
  const exportDebuggerLogs = (format: 'json' | 'ndjson' | 'txt') => {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const filenameBase = `debugger_logs_${environment}_${ts}`;
    let blob: Blob;
    if (format === 'json') {
      blob = new Blob([JSON.stringify({ logs: debugLogs }, null, 2)], { type: 'application/json' });
      triggerDownload(`${filenameBase}.json`, blob);
      return;
    }
    if (format === 'ndjson') {
      const nd = debugLogs.map((l:any) => JSON.stringify(l)).join('\n');
      blob = new Blob([nd], { type: 'application/x-ndjson' });
      triggerDownload(`${filenameBase}.ndjson`, blob);
      return;
    }
    const txt = debugLogs.map((l:any) => {
      const seg: string[] = [];
      seg.push(`[${new Date(l.created_at).toISOString()}] ${l.action}`);
      if (l.request) {
        seg.push(`→ ${l.request.method || ''} ${l.request.url || ''}`);
        if (l.request.headers) seg.push(`headers: ${JSON.stringify(l.request.headers)}`);
        if (l.request.body) seg.push(`body: ${typeof l.request.body === 'string' ? l.request.body : JSON.stringify(l.request.body)}`);
      }
      if (l.response) {
        seg.push(`← status: ${l.response.status ?? ''}`);
        if (l.response.headers) seg.push(`resp-headers: ${JSON.stringify(l.response.headers)}`);
        if (typeof l.response.body !== 'undefined') seg.push(`resp-body: ${typeof l.response.body === 'string' ? l.response.body : JSON.stringify(l.response.body)}`);
      }
      if (l.error) seg.push(`error: ${l.error}`);
      return seg.join('\n');
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

  const handleTemplateSelect = (templateName: string) => {
    setSelectedTemplate(templateName);
    const template = templates[templateName];
    if (template && templateName !== "custom") {
      setMethod(template.method);
      setPath(template.path);
      setParams(Object.entries(template.params).map(([k, v]) => `${k}=${v}`).join('&'));
      setHeaders('');
      setBody('');
    } else if (templateName === "custom") {
      setMethod('GET');
      setPath('');
      setParams('');
      setHeaders('');
      setBody('');
    }
  };

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      setTimeout(() => setCopied(''), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleDebug = async () => {
    setStdError('');
    // Scope guard for Quick Templates (only when a non-custom template is selected).
    // We no longer block the request; we only show a warning + optional reconnect modal.
    try {
      const tpl = selectedTemplate && selectedTemplate !== 'custom' ? selectedTemplate : null;
      if (tpl) {
        const required = REQUIRED_SCOPES_BY_TEMPLATE[tpl] || [];
        // Always use the scopes from the currently selected account/tokenInfo.
        // Admin-level scopes may differ or be stale and would give false negatives.
        if (!tokenInfo || !Array.isArray(tokenInfo.scopes)) {
          // Token info not loaded yet – skip scope warning to avoid false negatives.
        } else {
          const userScopes: string[] = tokenInfo.scopes || [];
          const missing = required.filter(r => !(userScopes || []).includes(r));
          if (missing.length > 0) {
            setStdError(`Missing required scopes: ${missing.join(', ')}`);
            setReconnectScopes(missing);
            setShowReconnect(true);
            // Log to token terminal (production only, behind flag)
            if (FEATURE_TOKEN_INFO && environment === 'production') {
              try {
                await api.post('/admin/ebay/tokens/logs/blocked-scope?env=production', {
                  template: tpl,
                  path,
                  required_scopes: required,
                  missing_scopes: missing,
                });
              } catch {}
            }
            // Do NOT return here – still send the request to eBay so the debugger remains usable.
          }
        }
      }
    } catch {}

    if (totalTestingMode) {
      // Handle raw request via backend
      if (!rawRequest.trim()) {
        setError('Raw request is required');
        return;
      }
      setLoading(true);
      setError('');
      setStdError('');
      setRawError('');
      setResponse(null);
      try {
        const res = await api.post(`/ebay/debug/raw?environment=${environment}`, { raw: rawRequest });
        setResponse(res.data);
      } catch (err:any) {
        console.error('Raw debug request failed:', err);
        setRawError(err?.response?.data?.detail || err?.message || 'Failed to make raw debug request');
      } finally {
        setLoading(false);
      }
      return;
    }

    if (!path) {
      setStdError('Path is required');
      return;
    }

    setLoading(true);
    setError('');
    setResponse(null);

    try {
      const paramsObj: Record<string, string> = {};
      if (params) {
        params.split('&').forEach(pair => {
          const [key, value] = pair.split('=');
          if (key && value) {
            paramsObj[key.trim()] = value.trim();
          }
        });
      }

      const headersObj: Record<string, string> = {};
      if (headers) {
        headers.split(',').forEach(pair => {
          const [key, value] = pair.split(':');
          if (key && value) {
            headersObj[key.trim()] = value.trim();
          }
        });
      }

      const queryParams = new URLSearchParams({
        method,
        path,
        environment: environment,
        ...(params ? { params: Object.entries(paramsObj).map(([k, v]) => `${k}=${v}`).join('&') } : {}),
        ...(headers ? { headers: Object.entries(headersObj).map(([k, v]) => `${k}: ${v}`).join(', ') } : {}),
        ...(body ? { body } : {}),
        ...(selectedTemplate && selectedTemplate !== "custom" ? { template: selectedTemplate } : {})
      });

      if (selectedAccountId) {
        queryParams.set('account_id', selectedAccountId);
      }
      const res = await api.post(`/ebay/debug?${queryParams.toString()}`, {});
      setResponse(res.data);
      // refresh terminal logs shortly after send
      try { setTimeout(() => { void loadDebuggerLogs(); }, 200); } catch {}
    } catch (err: any) {
      console.error('Debug request failed:', err);
      setStdError(err.response?.data?.detail || 'Failed to make debug request');
      try { setTimeout(() => { void loadDebuggerLogs(); }, 200); } catch {}
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (statusCode: number) => {
    if (statusCode >= 200 && statusCode < 300) return 'bg-green-100 text-green-800 border-green-200';
    if (statusCode >= 400 && statusCode < 500) return 'bg-red-100 text-red-800 border-red-200';
    if (statusCode >= 500) return 'bg-red-100 text-red-800 border-red-200';
    return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  };

  const getStatusEmoji = (statusCode: number) => {
    if (statusCode >= 200 && statusCode < 300) return '🟢';
    if (statusCode >= 400) return '🔴';
    return '🟡';
  };

  return (
    <div className="space-y-4">
      {/* Quick Token Info Button */}
      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-lg">🔑 Quick Token Info</h3>
              <p className="text-sm text-gray-600">View full token details, scopes, and connection information</p>
            </div>
            <Button 
              onClick={() => {
                setActiveTab('token-info');
                if (!tokenInfo) {
                  loadTokenInfo();
                }
              }}
              size="sm"
              className="h-8 px-3 text-xs"
              variant="outline"
            >
              View Token Info
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Tabs for Debugger and Token Info */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'debugger' | 'token-info')}>
        <TabsList className="grid w-full max-w-xs grid-cols-2 text-xs mb-2">
          <TabsTrigger value="debugger" className="h-8 py-1 text-xs">🔧 API Debugger</TabsTrigger>
          <TabsTrigger value="token-info" className="h-8 py-1 text-xs">🔑 Token Info</TabsTrigger>
        </TabsList>

        <TabsContent value="debugger" className="space-y-4">
          {/* Existing Debugger Content */}
          <Card>
        <CardHeader>
          <CardTitle>🔧 eBay API Debugger</CardTitle>
          <CardDescription>
            Test eBay API requests directly. Check token validity, diagnose errors, and see full request/response data.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Environment + Account Selector + Token badge */}
          <div className="flex flex-col gap-3 p-3 bg-gray-50 rounded-lg border">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Label htmlFor="debugger-env" className="font-medium">
                  Environment:
                </Label>
                <Badge variant={environment === 'sandbox' ? 'default' : 'destructive'}>
                  {environment === 'sandbox' ? '🧪 Sandbox' : '🚀 Production'}
                </Badge>
              </div>
              <div className="flex items-center gap-3">
              <Label htmlFor="debugger-env" className="text-sm text-gray-600">
                Sandbox
              </Label>
              <Switch
                id="debugger-env"
                checked={environment === 'production'}
                onCheckedChange={(checked) => {
                  const newEnv = checked ? 'production' : 'sandbox';
                  handleEnvironmentChange(newEnv);
                }}
              />
              <Label htmlFor="debugger-env" className="text-sm text-gray-600">
                Production
              </Label>
            </div>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div className="text-xs font-medium text-gray-700">eBay account:</div>
              <div className="flex items-center gap-2 flex-1">
                {accountsLoading ? (
                  <div className="text-xs text-gray-500">Loading accounts...</div>
                ) : accountsError ? (
                  <div className="text-xs text-red-500">{accountsError}</div>
                ) : accounts.length === 0 ? (
                  <div className="text-xs text-gray-500">No eBay accounts. Connect to eBay first.</div>
                ) : (
                  <Select
                    value={selectedAccountId || accounts[0]?.id}
                    onValueChange={(val) => {
                      setSelectedAccountId(val);
                      // Refresh lightweight token info when switching accounts
                      void loadTokenInfo(environment, { skipIdentityTest: true });
                    }}
                  >
                    <SelectTrigger className="w-full sm:w-64 h-8 text-xs">
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
                )}
              </div>
            </div>

            {/* Compact token status for selected account */}
            <div className="mt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-[11px] text-gray-600">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">Token:</span>
                {tokenInfoLoading ? (
                  <span>Loading…</span>
                ) : tokenInfo && tokenInfo.token_full ? (
                  <span className="font-mono break-all">
                    {tokenInfo.token_full.slice(0, 16)}…
                  </span>
                ) : (
                  <span className="text-gray-400">Not loaded</span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span>
                  Status:
                  {' '}
                  {tokenInfo && tokenInfo.ebay_connected ? (
                    <span className="text-green-600 font-medium">live</span>
                  ) : (
                    <span className="text-red-600 font-medium">not connected</span>
                  )}
                </span>
                {tokenInfo?.token_expires_at && (
                  <span className="text-gray-500">
                    expires at {tokenInfo.token_expires_at}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Mode Toggle */}
          <div className="flex items-center gap-2 text-xs">
            <Button
              variant={!totalTestingMode ? "default" : "outline"}
              onClick={() => setTotalTestingMode(false)}
              size="sm"
              className="h-8 px-3 text-xs"
            >
              Standard Mode
            </Button>
            <Button
              variant={totalTestingMode ? "default" : "outline"}
              onClick={() => setTotalTestingMode(true)}
              size="sm"
              className="h-8 px-3 text-xs"
            >
              Total Testing Mode
            </Button>
          </div>

          {totalTestingMode ? (
            /* Total Testing Mode */
              <div className="space-y-1">
                <Label className="text-xs font-medium">Raw Request (Full URL + Headers + Body)</Label>
              <Textarea
                placeholder={environment === 'sandbox' 
                  ? "GET https://api.sandbox.ebay.com/identity/v1/oauth2/userinfo\nAuthorization: Bearer v^1.1#...\nX-EBAY-C-MARKETPLACE-ID: EBAY_US"
                  : "GET https://api.ebay.com/identity/v1/oauth2/userinfo\nAuthorization: Bearer v^1.1#...\nX-EBAY-C-MARKETPLACE-ID: EBAY_US"}
                value={rawRequest}
                onChange={(e) => setRawRequest(e.target.value)}
                rows={8}
                className="font-mono text-sm"
              />
              {rawError && (
                <Alert variant="destructive"><AlertDescription>{rawError}</AlertDescription></Alert>
              )}
              <p className="text-xs text-gray-500">
                Paste full request here (method, URL, headers, body). One line per header.
              </p>
            </div>
          ) : (
            /* Standard Mode */
            <>
              {/* Compact parameter row: Templates + Method + Path + Query + Headers */}
              <div className="flex flex-wrap items-end gap-3 text-xs">
                {/* Quick Templates */}
                <div className="flex-1 min-w-[220px]">
                  <Label className="text-xs font-medium">Quick Templates</Label>
                  <Select value={selectedTemplate || "custom"} onValueChange={handleTemplateSelect}>
                    <SelectTrigger className="mt-1 h-8 text-xs">
                      <SelectValue placeholder="Select a template or use custom" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="custom">Custom Request</SelectItem>
                      {Object.entries(templates).map(([key, template]) => (
                        <SelectItem key={key} value={key}>
                          {template.name} - {template.description}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Method */}
                <div className="w-24">
                  <Label className="text-xs font-medium">Method</Label>
                  <Select value={method} onValueChange={setMethod}>
                    <SelectTrigger className="mt-1 h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="GET">GET</SelectItem>
                      <SelectItem value="POST">POST</SelectItem>
                      <SelectItem value="PUT">PUT</SelectItem>
                      <SelectItem value="DELETE">DELETE</SelectItem>
                      <SelectItem value="PATCH">PATCH</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* API Path */}
                <div className="flex-[2] min-w-[260px]">
                  <Label className="text-xs font-medium">API Path *</Label>
                  <Input
                    className="mt-1 h-8 text-xs"
                    placeholder="/sell/fulfillment/v1/order"
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                  />
                </div>

                {/* Query Parameters */}
                <div className="flex-1 min-w-[220px]">
                  <Label className="text-xs font-medium">Query Parameters</Label>
                  <Input
                    className="mt-1 h-8 text-xs"
                    placeholder="limit=1&filter=orderStatus:COMPLETED"
                    value={params}
                    onChange={(e) => setParams(e.target.value)}
                  />
                  <p className="text-[11px] text-gray-500">Format: key1=value1&key2=value2</p>
                </div>

                {/* Headers */}
                <div className="flex-1 min-w-[240px]">
                  <Label className="text-xs font-medium">Additional Headers (optional)</Label>
                  <Input
                    className="mt-1 h-8 text-xs"
                    placeholder="X-EBAY-C-MARKETPLACE-ID: EBAY_US"
                    value={headers}
                    onChange={(e) => setHeaders(e.target.value)}
                  />
                  <p className="text-xs text-gray-500">Format: Header1: Value1, Header2: Value2</p>
                </div>
              </div>

              {/* Body */}
              {(method === 'POST' || method === 'PUT' || method === 'PATCH') && (
                <div className="space-y-2">
                  <Label>Request Body (JSON)</Label>
                  <Textarea
                    placeholder='{"key": "value"}'
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    rows={4}
                    className="font-mono text-sm"
                  />
                </div>
              )}
            </>
          )}

          {/* Error */}
          {stdError && (
            <Alert variant="destructive">
              <AlertDescription>{stdError}</AlertDescription>
            </Alert>
          )}

            {/* Raw Request Preview (one line + headers) */}
            {!totalTestingMode && (
              <div className="mb-3 p-3 bg-gray-50 rounded border">
                <Label className="text-xs text-gray-500 mb-1 block">Raw Request Preview</Label>
                <pre className="text-xs font-mono whitespace-pre-wrap break-all">{`${method} ${(() => {
                  const base = environment === 'sandbox' ? 'https://api.sandbox.ebay.com' : 'https://api.ebay.com';
                  const p = path.startsWith('http') ? path : (path.startsWith('/') ? `${base}${path}` : `${base}/${path}`);
                  const paramsObj: Record<string,string> = {};
                  (params||'').split('&').forEach((pair)=>{ const [k,v] = pair.split('='); if(k&&v) paramsObj[k.trim()] = v.trim(); });
                  const qs = new URLSearchParams(paramsObj).toString();
                  return qs ? `${p}?${qs}` : p;
                })()}`}
{Object.entries((() => {
  const hdrs: Record<string,string> = {};
  (headers||'').split(',').forEach((pair)=>{ const [k,v] = pair.split(':'); if(k&&v) hdrs[k.trim()] = v.trim(); });
  // We always add Authorization/Accept/Content-Type
  hdrs['Authorization'] = 'Bearer ***';
  hdrs['Accept'] = 'application/json';
  if(['POST','PUT','PATCH'].includes(method.toUpperCase())) hdrs['Content-Type']='application/json';
  return hdrs;
})()).map(([k,v])=>`\n${k}: ${v}`).join('')}
{['POST','PUT','PATCH'].includes(method.toUpperCase()) && body ? `\n\n${body}` : ''}
</pre>
              </div>
            )}
            {/* Submit Button */}
            <Button onClick={handleDebug} disabled={loading || (!totalTestingMode && !path) || (totalTestingMode && !rawRequest.trim())}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending Request...
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Send Request
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Request Context */}
      {response && response.request_context && (
        <Card className="border-blue-200 bg-blue-50">
          <CardHeader>
            <CardTitle className="text-lg">🔍 REQUEST CONTEXT</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-semibold">User:</span> {response.request_context.user_email} (ID: {response.request_context.user_id})
              </div>
              <div>
                <span className="font-semibold">Environment:</span> {response.request_context.environment}
              </div>
              <div className="col-span-2">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="font-semibold">eBay Token:</span>
                    <div className="font-mono text-xs mt-1 break-all bg-white p-2 rounded border">
                      {response.request_context.token_full || response.request_context.token}
                    </div>
                    {response.request_context.token_version && (
                      <span className="text-gray-500 ml-2">(v{response.request_context.token_version})</span>
                    )}
                    {response.request_context.token_expires_at && (
                      <span className="text-gray-500 ml-2">(expires: {new Date(response.request_context.token_expires_at).toLocaleDateString()})</span>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(response.request_context?.token_full || response.request_context?.token || '', 'token')}
                  >
                    {copied === 'token' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              <div className="col-span-2">
                <span className="font-semibold">Scopes:</span>
                <div className="mt-1">
                  {response.request_context.scopes_full && response.request_context.scopes_full.length > 0 ? (
                    <div className="space-y-1">
                      <div className="text-xs text-gray-600">{response.request_context.scopes_display}</div>
                      <details className="text-xs">
                        <summary className="cursor-pointer text-blue-600 hover:text-blue-800">Show full scope list</summary>
                        <ul className="list-disc list-inside mt-1 space-y-1">
                          {response.request_context.scopes_full.map((scope, idx) => (
                            <li key={idx} className="font-mono">{scope}</li>
                          ))}
                        </ul>
                      </details>
                    </div>
                  ) : (
                    <span className="text-red-600">None</span>
                  )}
                </div>
              </div>
              {response.request_context.missing_scopes && response.request_context.missing_scopes.length > 0 && (
                <div className="col-span-2">
                  <Alert variant="destructive">
                    <AlertDescription>
                      <span className="font-semibold">⚠️ Missing required scopes:</span>
                      <ul className="list-disc list-inside mt-1">
                        {response.request_context.missing_scopes.map((scope, idx) => (
                          <li key={idx} className="font-mono text-xs">{scope}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Response - COLUMNS instead of TABS */}
      {response && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Response</CardTitle>
              <Badge className={getStatusColor(response.response.status_code)}>
                {getStatusEmoji(response.response.status_code)} {response.response.status_code} {response.response.status_text}
              </Badge>
            </div>
            <CardDescription>
              Response time: {response.response.response_time_ms} ms
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Full URL in one line */}
            <div className="mb-4 p-3 bg-gray-50 rounded border">
              <div className="flex items-center justify-between">
                <div className="flex-1 overflow-x-auto">
                  <Label className="text-xs text-gray-500 mb-1 block">Full Request URL (one line)</Label>
                  <p className="font-mono text-sm break-all">{response.request.url_full || response.request.url}</p>
                </div>
                <div className="flex items-center gap-2 ml-2">
                  <Button variant="outline" size="sm" onClick={() => setLineWrap(prev => !prev)}>
                    {lineWrap ? 'Disable wrap' : 'Wrap lines'}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(response.request.url_full || response.request.url, 'url')}
                  >
                    {copied === 'url' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </div>

            {/* Three Columns: Request | Response | eBay Headers */}
            <div className="grid grid-cols-3 gap-4">
              {/* Column 1: Request */}
              <div className="space-y-2">
                <h3 className="font-semibold text-sm border-b pb-2">Request</h3>
                <ScrollArea className="h-[600px] w-full rounded-md border bg-gray-50 p-3">
                  <div className="space-y-3">
                    <div>
                      <Label className="text-xs text-gray-500">Method</Label>
                      <p className="font-mono text-xs">{response.request.method}</p>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-500">URL</Label>
                      <p className="font-mono text-xs break-all overflow-x-auto">{response.request.url}</p>
                    </div>
                    {Object.keys(response.request.params).length > 0 && (
                      <div>
                        <Label className="text-xs text-gray-500">Query Parameters</Label>
                        <pre className={`text-xs bg-white p-2 rounded overflow-auto border ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                          {JSON.stringify(response.request.params, null, 2)}
                        </pre>
                      </div>
                    )}
                    <div>
                      <Label className="text-xs text-gray-500">Headers</Label>
                      <pre className={`text-xs bg-white p-2 rounded overflow-auto border ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                        {JSON.stringify(response.request.headers, null, 2)}
                      </pre>
                    </div>
                    {response.request.body && (
                      <div>
                        <Label className="text-xs text-gray-500">Body</Label>
                        <pre className={`text-xs bg-white p-2 rounded overflow-auto border ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                          {typeof response.request.body === 'string' 
                            ? response.request.body 
                            : JSON.stringify(response.request.body, null, 2)}
                        </pre>
                      </div>
                    )}
                    {response.request.curl_command && (
                      <div>
                        <Label className="text-xs text-gray-500">cURL Command</Label>
                        <pre className={`text-xs bg-white p-2 rounded overflow-auto border ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                          {response.request.curl_command}
                        </pre>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>

              {/* Column 2: Response */}
              <div className="space-y-2">
                <h3 className="font-semibold text-sm border-b pb-2">Response</h3>
                <ScrollArea className="h-[600px] w-full rounded-md border bg-gray-50 p-3">
                  <div className="space-y-3">
                    <div>
                      <Label className="text-xs text-gray-500">Status</Label>
                      <p className="font-mono text-xs">
                        {response.response.status_code} {response.response.status_text}
                      </p>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-500">Response Body</Label>
                      <pre className={`text-xs bg-white p-2 rounded overflow-auto border max-h-[500px] ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                        {typeof response.response.body === 'string'
                          ? response.response.body
                          : JSON.stringify(response.response.body, null, 2)}
                      </pre>
                    </div>
                    {response.response.status_code >= 400 && (
                      <Alert variant="destructive" className="text-xs">
                        <AlertDescription>
                          {typeof response.response.body === 'object' && response.response.body.errors
                            ? JSON.stringify(response.response.body.errors, null, 2)
                            : 'Request failed. Check response body for details.'}
                        </AlertDescription>
                      </Alert>
                    )}
                  </div>
                </ScrollArea>
              </div>

              {/* Column 3: eBay Headers */}
              <div className="space-y-2">
                <h3 className="font-semibold text-sm border-b pb-2">eBay Headers</h3>
                <ScrollArea className="h-[600px] w-full rounded-md border bg-gray-50 p-3">
                  <div className="space-y-3">
                    {Object.keys(response.response.ebay_headers).length > 0 ? (
                      <>
                        <div>
                          <Label className="text-xs text-gray-500">eBay-Specific Headers</Label>
                          <pre className={`text-xs bg-white p-2 rounded overflow-auto border ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                            {JSON.stringify(response.response.ebay_headers, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <Label className="text-xs text-gray-500">All Response Headers</Label>
                          <pre className={`text-xs bg-white p-2 rounded overflow-auto border max-h-[400px] ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                            {JSON.stringify(response.response.headers, null, 2)}
                          </pre>
                        </div>
                      </>
                    ) : (
                      <div>
                        <Label className="text-xs text-gray-500">All Response Headers</Label>
                        <pre className={`text-xs bg-white p-2 rounded overflow-auto border ${lineWrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'} overflow-x-auto`}>
                          {JSON.stringify(response.response.headers, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>
          </CardContent>
        </Card>
        )}

        {/* Debugger Terminal (last 100) */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Debugger Terminal (last 100)</CardTitle>
                <CardDescription>Live request/response events from the Debugger. No secrets are stored.</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => exportDebuggerLogs('json')}>Save JSON</Button>
                <Button size="sm" variant="outline" onClick={() => exportDebuggerLogs('ndjson')}>Save NDJSON</Button>
                <Button size="sm" variant="outline" onClick={() => exportDebuggerLogs('txt')}>Save TXT</Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {debugLogsLoading && <div className="text-sm text-gray-600">Loading...</div>}
            <ScrollArea className="h-80 rounded border bg-gray-900 p-4 font-mono text-xs">
              {debugLogs.length === 0 ? (
                <div className="text-gray-400">No debugger events yet.</div>
              ) : (
                <div className="space-y-3">
                  {debugLogs.map((log:any)=> (
                    <div key={log.id} className="border-b border-gray-800 pb-3">
                      <div className="flex items-center justify-between text-gray-400">
                        <span>[{new Date(log.created_at).toLocaleString()}]</span>
                        <span>{log.action}</span>
                      </div>
                      {log.request && (
                        <div className="mt-1 text-green-300">
                          → {log.request.method} {log.request.url}
                          {log.request.headers && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-24 whitespace-pre-wrap break-words">{JSON.stringify(log.request.headers, null, 2)}</pre>
                          )}
                          {log.request.body && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-24 whitespace-pre-wrap break-words">{typeof log.request.body === 'string' ? log.request.body : JSON.stringify(log.request.body, null, 2)}</pre>
                          )}
                        </div>
                      )}
                      {log.response && (
                        <div className="mt-1 text-blue-300">
                          ← status: {log.response.status}
                          {log.response.headers && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-24 whitespace-pre-wrap break-words">{JSON.stringify(log.response.headers, null, 2)}</pre>
                          )}
                          {typeof log.response.body !== 'undefined' && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto overflow-x-auto max-h-32 whitespace-pre-wrap break-words">{typeof log.response.body === 'string' ? log.response.body : JSON.stringify(log.response.body, null, 2)}</pre>
                          )}
                        </div>
                      )}
                      {log.error && (
                        <div className="mt-1 text-red-300">error: {log.error}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Reconnect with required scopes (pre-flight) */}
        <Dialog open={showReconnect} onOpenChange={(o)=> setShowReconnect(o)}>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>Reconnect with required scopes</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 text-sm">
              <div className="text-gray-700">Scopes we are about to request:</div>
              <div className="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
                {reconnectScopes.map((s,i)=> (
                  <span key={i} className="text-xs px-2 py-0.5 border rounded bg-gray-50">{s}</span>
                ))}
              </div>
              {reconnectUrl && (
                <div className="p-3 bg-gray-50 rounded border font-mono text-xs overflow-x-auto">
                  GET {reconnectUrl}
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={()=> setShowReconnect(false)}>Cancel</Button>
              <Button variant="outline" onClick={async ()=> {
                try {
                  const redirectUri = `${window.location.origin}/ebay/callback`;
                  const union = Array.from(new Set([...(reconnectScopes||[]), ...MY_SCOPES]));
                  const { data } = await api.post(`/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`, { scopes: union });
                  localStorage.setItem('ebay_oauth_environment', environment);
                  window.location.href = data.authorization_url;
                } catch {}
              }}>Request all my scopes</Button>
              <Button onClick={()=> { if (reconnectUrl) { localStorage.setItem('ebay_oauth_environment', environment); window.location.href = reconnectUrl; } }}>Proceed to eBay</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        </TabsContent>

        <TabsContent value="token-info" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>🔑 eBay Token Information</CardTitle>
              <CardDescription>
                Full token details, scopes, and connection information
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Environment Selector */}
              <div className="mb-4 flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                <div className="flex items-center gap-3">
                  <Label htmlFor="token-info-env" className="font-medium">
                    Environment:
                  </Label>
                  <Badge variant={environment === 'sandbox' ? 'default' : 'destructive'}>
                    {environment === 'sandbox' ? '🧪 Sandbox' : '🚀 Production'}
                  </Badge>
                </div>
                <div className="flex items-center gap-3">
                  <Label htmlFor="token-info-env" className="text-sm text-gray-600">
                    Sandbox
                  </Label>
                  <Switch
                    id="token-info-env"
                    checked={environment === 'production'}
                    onCheckedChange={(checked) => {
                      const newEnv = checked ? 'production' : 'sandbox';
                      handleEnvironmentChange(newEnv);
                    }}
                  />
                  <Label htmlFor="token-info-env" className="text-sm text-gray-600">
                    Production
                  </Label>
                </div>
              </div>

          {tokenInfoLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin mr-2" />
                  Loading token information...
                </div>
              ) : error ? (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : tokenInfo ? (
                <div className="space-y-4">
          {environment === 'production' && (
                    <div className="space-y-2 p-3 bg-amber-50 border border-amber-200 rounded">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label className="text-sm font-semibold">Token Info (Production)</Label>
                          <p className="text-xs text-gray-600">User access token (~2h) is used for API calls. Refresh token (long-lived) is used only to obtain a new user access token.</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button size="sm" variant="outline" onClick={loadAdminTokenInfo} disabled={refreshingAdmin}>Load</Button>
                          <Button size="sm" onClick={refreshAdminToken} disabled={refreshingAdmin}>
                            {refreshingAdmin ? <><Loader2 className="mr-1 h-3 w-3 animate-spin"/>Refreshing...</> : 'Manual User Token Refresh'}
                          </Button>
                        </div>
                      </div>
                      {adminTokenInfo && !adminTokenInfo.error && (
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div>
                            <Label className="text-xs text-gray-500">User access token (~2h)</Label>
                            <div className="font-mono text-xs p-2 bg-white border rounded">{adminTokenInfo.access_token_masked || '—'}</div>
                            <div className="text-xs text-gray-600 mt-1">Expires at (UTC): {adminTokenInfo.access_expires_at || '—'} {adminTokenInfo.access_ttl_sec != null && `(ttl ${adminTokenInfo.access_ttl_sec}s)`}</div>
                          </div>
                          <div>
                            <Label className="text-xs text-gray-500">Refresh token (long-lived)</Label>
                            <div className="font-mono text-xs p-2 bg-white border rounded">{adminTokenInfo.refresh_token_masked || '—'}</div>
                            <div className="text-xs text-gray-600 mt-1">
                              Refresh expires at (UTC): {adminTokenInfo.refresh_expires_at || '—'}
                              {typeof adminTokenInfo.refresh_ttl_sec === 'number' && (
                                <span> (ttl {adminTokenInfo.refresh_ttl_sec}s)</span>
                              )}
                              {!adminTokenInfo.refresh_expires_at && (
                                <span className="ml-1 text-gray-500">Exact expiry not returned by eBay in this environment</span>
                              )}
                            </div>
                          </div>
                          <div className="col-span-2">
                            <Label className="text-xs text-gray-500">Scopes (from authorization)</Label>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {(adminTokenInfo.scopes || []).map((s:string, i:number)=> (
                                <span key={i} className="text-xs px-2 py-0.5 border rounded bg-gray-50">{s}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                      {adminTokenInfo && adminTokenInfo.error && (
                        <Alert variant="destructive"><AlertDescription>{String(adminTokenInfo.error)}</AlertDescription></Alert>
                      )}
                    </div>
                  )}
                  {/* Condensed User Summary */}
              <div className="p-2 bg-blue-50 rounded-lg border border-blue-200 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">User:</span> <span>{tokenInfo.user_email}</span>
                      <span>•</span>
                      <span className="font-semibold">eBay:</span> <span>{tokenInfo.ebay_username || '—'}{tokenInfo.ebay_user_id ? ` (${tokenInfo.ebay_user_id})` : ''}</span>
                      <span>•</span>
                      <span className="font-semibold">Env:</span> <span>{tokenInfo.ebay_environment}</span>
                      <span>•</span>
                      <span className="font-semibold">Status:</span> <span>{tokenInfo.ebay_connected ? 'Connected' : 'Not Connected'}</span>
                    </div>
                  </div>

                  {/* Token cards (local view of access token) */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm font-semibold">User access token (~2h)</Label>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => copyToClipboard(tokenInfo.token_full, 'token-full')}
                      >
                        {copied === 'token-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                    <div className="p-3 bg-gray-50 rounded border font-mono text-xs break-all">
                      {tokenInfo.token_full}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>Length: {tokenInfo.token_length} characters</span>
                      {tokenInfo.token_version && <span>Version: {tokenInfo.token_version}</span>}
                      {tokenInfo.token_expires_at && (
                        <span>Expires: {new Date(tokenInfo.token_expires_at).toLocaleString()}</span>
                      )}
                    </div>
                  </div>

                  {/* Scopes */}
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">
                      Scopes ({tokenInfo.scopes_count})
                    </Label>
                    <div className="p-3 bg-gray-50 rounded border">
                      <div className="text-sm mb-2">
                        <span className="font-semibold">Display:</span> {tokenInfo.scopes_display || 'None'}
                      </div>
                      <details className="mt-2">
                        <summary className="cursor-pointer text-blue-600 hover:text-blue-800 text-sm font-semibold">
                          Show Full Scope List
                        </summary>
                        <ul className="list-disc list-inside mt-2 space-y-1">
                          {tokenInfo.scopes.length > 0 ? (
                            tokenInfo.scopes.map((scope, idx) => (
                              <li key={idx} className="font-mono text-xs text-gray-700">{scope}</li>
                            ))
                          ) : (
                            <li className="text-red-600 text-sm">No scopes found</li>
                          )}
                        </ul>
                      </details>
                    </div>
                  </div>

                  {/* Refresh Button */}
                  <Button 
                    onClick={() => loadTokenInfo()} 
                    variant="outline" 
                    className="w-full"
                    disabled={tokenInfoLoading || tokenInfoRequestLoading}
                  >
                    <Loader2 className={`h-4 w-4 mr-2 ${(tokenInfoLoading || tokenInfoRequestLoading) ? 'animate-spin' : ''}`} />
                    {tokenInfoRequestLoading ? 'Testing API...' : 'Refresh Token Info & Test API'}
                  </Button>

                  {/* Admin: Accounts + Scopes vs Catalog (production only) */}
                  {FEATURE_TOKEN_INFO && environment === 'production' && (
                    <Card className="mt-4">
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle>Accounts &amp; Scopes (Admin)</CardTitle>
                            <CardDescription>
                              For this org: all eBay accounts, stored scopes, and comparison with scope catalog.
                            </CardDescription>
                          </div>
                          <Button size="sm" variant="outline" onClick={loadAdminAccountsScopes} disabled={accountsScopesLoading}>
                            {accountsScopesLoading ? <><Loader2 className="mr-1 h-3 w-3 animate-spin"/>Reloading...</> : 'Reload'}
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4 text-sm">
                        {accountsScopesError && (
                          <Alert variant="destructive"><AlertDescription>{accountsScopesError}</AlertDescription></Alert>
                        )}
                        {accountsScopes && (
                          <>
                            <div className="text-xs text-gray-600 mb-1">
                              Scope catalog: {accountsScopes.scope_catalog.length} scopes
                            </div>
                            <details className="mb-3">
                              <summary className="cursor-pointer text-blue-600 hover:text-blue-800 text-xs">Show scope catalog</summary>
                              <ul className="mt-2 space-y-1 list-disc list-inside">
                                {accountsScopes.scope_catalog.map((s) => (
                                  <li key={s.scope} className="font-mono text-xs text-gray-700">
                                    {s.scope}
                                  </li>
                                ))}
                              </ul>
                            </details>
                            {accountsScopes.accounts.length === 0 ? (
                              <div className="text-gray-600 text-sm">No eBay accounts found for this org.</div>
                            ) : (
                              <div className="space-y-3">
                                {accountsScopes.accounts.map((acc) => (
                                  <div key={acc.id} className="p-3 border rounded bg-gray-50">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <div>
                                        <div className="font-semibold">{acc.house_name || acc.username || acc.id}</div>
                                        <div className="text-xs text-gray-600">eBay: {acc.username || '—'} ({acc.ebay_user_id})</div>
                                        {acc.connected_at && (
                                          <div className="text-xs text-gray-500">Connected at: {new Date(acc.connected_at).toLocaleString()}</div>
                                        )}
                                      </div>
                                      <div className="text-right text-xs">
                                        <div>Scopes: {acc.scopes_count} / {accountsScopes.scope_catalog.length}</div>
                                        <div>
                                          {acc.has_all_catalog_scopes ? (
                                            <span className="text-green-600 font-semibold">Full catalog granted</span>
                                          ) : (
                                            <span className="text-amber-600 font-semibold">Missing {acc.missing_catalog_scopes.length} scopes</span>
                                          )}
                                        </div>
                                        {acc.token && (
                                          <div className="mt-1 text-xs text-gray-500">
                                            Access expires: {acc.token.access_expires_at || '—'}
                                            {acc.token.has_refresh_token ? ' • has refresh token' : ''}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                    <details className="mt-2">
                                      <summary className="cursor-pointer text-blue-600 hover:text-blue-800 text-xs">Show account scopes</summary>
                                      <div className="mt-1 flex flex-wrap gap-1">
                                        {acc.scopes.length === 0 ? (
                                          <span className="text-xs text-red-600">No scopes stored</span>
                                        ) : (
                                          acc.scopes.map((s) => (
                                            <span key={s} className="text-xs px-2 py-0.5 border rounded bg-white font-mono">{s}</span>
                                          ))
                                        )}
                                      </div>
                                    </details>
                                    {!acc.has_all_catalog_scopes && acc.missing_catalog_scopes.length > 0 && (
                                      <details className="mt-2">
                                        <summary className="cursor-pointer text-amber-700 hover:text-amber-900 text-xs">Show missing catalog scopes</summary>
                                        <ul className="mt-1 list-disc list-inside">
                                          {acc.missing_catalog_scopes.map((s) => (
                                            <li key={s} className="text-xs font-mono text-amber-800">{s}</li>
                                          ))}
                                        </ul>
                                      </details>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                        {!accountsScopes && !accountsScopesLoading && !accountsScopesError && (
                          <div className="text-xs text-gray-500">Click "Reload" to load accounts/scopes from admin API.</div>
                        )}
                      </CardContent>
                    </Card>
                  )}
                </div>
              ) : (
                <Alert>
                  <AlertDescription>
                    Click "Refresh Token Info" to load token information.
                  </AlertDescription>
                </Alert>
              )}

              {/* Token Terminal Log (persistent, last 100) */}
              {environment === 'production' && (
                <Card className="mt-4">
                  <CardHeader>
                    <CardTitle>🖥️ Token Terminal Log</CardTitle>
                    <CardDescription>Last 100 token actions (manual refresh, info views). No secrets are stored or shown.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-sm text-gray-600">Environment: Production</div>
                      <Button size="sm" variant="outline" onClick={loadTokenLogs} disabled={logsLoading}>
                        {logsLoading ? <><Loader2 className="mr-1 h-3 w-3 animate-spin"/>Reloading...</> : 'Reload'}
                      </Button>
                    </div>
                    <ScrollArea className="h-[320px] w-full rounded-md border bg-gray-900 p-4 font-mono text-xs">
                      {tokenLogs.length === 0 ? (
                        <div className="text-gray-400">No token actions yet.</div>
                      ) : (
                        <div className="space-y-3">
                          {tokenLogs.map((log) => (
                            <div key={log.id} className="border-b border-gray-700 pb-3 last:border-0">
                              <div className="text-gray-400 mb-1">[{new Date(log.created_at).toLocaleString()}] {log.action}</div>
                              {log.request?.method && log.request?.url && (
                                <div className="text-green-300">→ {log.request.method} {log.request.url}</div>
                              )}
                              {typeof log.response?.status !== 'undefined' && (
                                <div className={log.response.status && log.response.status >= 400 ? 'text-red-300' : 'text-blue-300'}>
                                  ← status: {log.response.status}
                                </div>
                              )}
                              {log.error && (
                                <div className="text-red-400">error: {log.error}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
                  </CardContent>
                </Card>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};
