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
import api from '../lib/apiClient';
// Feature flag with safe fallbacks: env var, localStorage, or ?tokeninfo=1
const FEATURE_TOKEN_INFO = (
  (import.meta.env.VITE_FEATURE_TOKEN_INFO === 'true') ||
  (typeof window !== 'undefined' && (localStorage.getItem('enable_token_info') === '1' || new URLSearchParams(window.location.search).get('tokeninfo') === '1'))
);
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
  
  // Token Info
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null);
  const [adminTokenInfo, setAdminTokenInfo] = useState<any | null>(null);
  const [refreshingAdmin, setRefreshingAdmin] = useState(false);
  const [tokenInfoLoading, setTokenInfoLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'debugger' | 'token-info'>('debugger');
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
    if (activeTab === 'debugger') {
      void loadDebuggerLogs();
      const id = setInterval(() => { if (!totalTestingMode) void loadDebuggerLogs(); }, 10000);
      return () => clearInterval(id);
    }
    if (activeTab === 'token-info') {
      loadTokenInfo();
      if (FEATURE_TOKEN_INFO && environment === 'production') {
        void loadAdminTokenInfo();
        void loadTokenLogs();
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
    } finally {
      setRefreshingAdmin(false);
    }
  };

  const loadTokenInfo = async (env?: 'sandbox' | 'production') => {
    const targetEnv = env || environment;
    setTokenInfoLoading(true);
    setError('');
    try {
      const res = await api.get(`/ebay/token-info?environment=${targetEnv}`);
      setTokenInfo(res.data);
      
      // Automatically test Identity API call if token is available
      if (res.data.token_full && res.data.ebay_connected) {
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
    // Scope guard for Quick Templates (only when a non-custom template is selected)
    try {
      const tpl = selectedTemplate && selectedTemplate !== 'custom' ? selectedTemplate : null;
      if (tpl) {
        const required = REQUIRED_SCOPES_BY_TEMPLATE[tpl] || [];
        const userScopes: string[] = (environment === 'production')
          ? (adminTokenInfo?.scopes || [])
          : (tokenInfo?.scopes || []);
        const missing = required.filter(r => !(userScopes || []).includes(r));
        if (missing.length > 0) {
          setError(`Missing required scopes: ${missing.join(', ')}`);
          // Log to token terminal (production only, behind flag)
          if (FEATURE_TOKEN_INFO && environment === 'production') {
            try { await api.post('/admin/ebay/tokens/logs/blocked-scope?env=production', {
              template: tpl,
              path,
              required_scopes: required,
              missing_scopes: missing,
            }); } catch {}
          }
          return; // Block send
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

      const res = await api.post(`/ebay/debug?${queryParams.toString()}`, {});
      setResponse(res.data);
    } catch (err: any) {
      console.error('Debug request failed:', err);
      setStdError(err.response?.data?.detail || 'Failed to make debug request');
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
              variant="default"
            >
              View Token Info
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Tabs for Debugger and Token Info */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'debugger' | 'token-info')}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="debugger">🔧 API Debugger</TabsTrigger>
          <TabsTrigger value="token-info">🔑 Token Info</TabsTrigger>
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
          {/* Environment Selector */}
          <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
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

          {/* Mode Toggle */}
          <div className="flex items-center space-x-4">
            <Button
              variant={!totalTestingMode ? "default" : "outline"}
              onClick={() => setTotalTestingMode(false)}
              size="sm"
            >
              Standard Mode
            </Button>
            <Button
              variant={totalTestingMode ? "default" : "outline"}
              onClick={() => setTotalTestingMode(true)}
              size="sm"
            >
              Total Testing Mode
            </Button>
          </div>

          {totalTestingMode ? (
            /* Total Testing Mode */
            <div className="space-y-2">
              <Label>Raw Request (Full URL + Headers + Body)</Label>
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
              {/* Template Selection */}
              <div className="space-y-2">
                <Label>Quick Templates</Label>
                <Select value={selectedTemplate || "custom"} onValueChange={handleTemplateSelect}>
                  <SelectTrigger>
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

              {/* Method and Path */}
              <div className="grid grid-cols-4 gap-4">
                <div className="space-y-2">
                  <Label>Method</Label>
                  <Select value={method} onValueChange={setMethod}>
                    <SelectTrigger>
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
                <div className="col-span-3 space-y-2">
                  <Label>API Path *</Label>
                  <Input
                    placeholder="/sell/fulfillment/v1/order"
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                  />
                </div>
              </div>

              {/* Query Parameters */}
              <div className="space-y-2">
                <Label>Query Parameters</Label>
                <Input
                  placeholder="limit=1&filter=orderStatus:COMPLETED"
                  value={params}
                  onChange={(e) => setParams(e.target.value)}
                />
                <p className="text-xs text-gray-500">Format: key1=value1&key2=value2</p>
              </div>

              {/* Headers */}
              <div className="space-y-2">
                <Label>Additional Headers (optional)</Label>
                <Input
                  placeholder="X-EBAY-C-MARKETPLACE-ID: EBAY_US"
                  value={headers}
                  onChange={(e) => setHeaders(e.target.value)}
                />
                <p className="text-xs text-gray-500">Format: Header1: Value1, Header2: Value2</p>
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
                <div className="flex-1">
                  <Label className="text-xs text-gray-500 mb-1 block">Full Request URL (one line)</Label>
                  <p className="font-mono text-sm break-all">{response.request.url_full || response.request.url}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => copyToClipboard(response.request.url_full || response.request.url, 'url')}
                  className="ml-2"
                >
                  {copied === 'url' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
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
                      <p className="font-mono text-xs break-all">{response.request.url}</p>
                    </div>
                    {Object.keys(response.request.params).length > 0 && (
                      <div>
                        <Label className="text-xs text-gray-500">Query Parameters</Label>
                        <pre className="text-xs bg-white p-2 rounded overflow-auto border">
                          {JSON.stringify(response.request.params, null, 2)}
                        </pre>
                      </div>
                    )}
                    <div>
                      <Label className="text-xs text-gray-500">Headers</Label>
                      <pre className="text-xs bg-white p-2 rounded overflow-auto border">
                        {JSON.stringify(response.request.headers, null, 2)}
                      </pre>
                    </div>
                    {response.request.body && (
                      <div>
                        <Label className="text-xs text-gray-500">Body</Label>
                        <pre className="text-xs bg-white p-2 rounded overflow-auto border">
                          {typeof response.request.body === 'string' 
                            ? response.request.body 
                            : JSON.stringify(response.request.body, null, 2)}
                        </pre>
                      </div>
                    )}
                    {response.request.curl_command && (
                      <div>
                        <Label className="text-xs text-gray-500">cURL Command</Label>
                        <pre className="text-xs bg-white p-2 rounded overflow-auto border">
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
                      <pre className="text-xs bg-white p-2 rounded overflow-auto border max-h-[500px]">
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
                          <pre className="text-xs bg-white p-2 rounded overflow-auto border">
                            {JSON.stringify(response.response.ebay_headers, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <Label className="text-xs text-gray-500">All Response Headers</Label>
                          <pre className="text-xs bg-white p-2 rounded overflow-auto border max-h-[400px]">
                            {JSON.stringify(response.response.headers, null, 2)}
                          </pre>
                        </div>
                      </>
                    ) : (
                      <div>
                        <Label className="text-xs text-gray-500">All Response Headers</Label>
                        <pre className="text-xs bg-white p-2 rounded overflow-auto border">
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
            <CardTitle>Debugger Terminal (last 100)</CardTitle>
            <CardDescription>Live request/response events from the Debugger. No secrets are stored.</CardDescription>
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
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-24">{JSON.stringify(log.request.headers, null, 2)}</pre>
                          )}
                          {log.request.body && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-24">{typeof log.request.body === 'string' ? log.request.body : JSON.stringify(log.request.body, null, 2)}</pre>
                          )}
                        </div>
                      )}
                      {log.response && (
                        <div className="mt-1 text-blue-300">
                          ← status: {log.response.status}
                          {log.response.headers && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-24">{JSON.stringify(log.response.headers, null, 2)}</pre>
                          )}
                          {typeof log.response.body !== 'undefined' && (
                            <pre className="mt-1 bg-gray-800 rounded p-2 text-xs overflow-auto max-h-32">{typeof log.response.body === 'string' ? log.response.body : JSON.stringify(log.response.body, null, 2)}</pre>
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
