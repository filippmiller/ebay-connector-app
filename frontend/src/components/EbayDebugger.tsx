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
  
  // Total Testing Mode
  const [totalTestingMode, setTotalTestingMode] = useState(false);
  const [rawRequest, setRawRequest] = useState<string>('');
  const [copied, setCopied] = useState<string>('');
  
  // Token Info
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null);
  const [tokenInfoLoading, setTokenInfoLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'debugger' | 'token-info'>('debugger');
  const [environment, setEnvironment] = useState<'sandbox' | 'production'>(() => {
    const saved = localStorage.getItem('ebay_environment');
    return (saved === 'production' ? 'production' : 'sandbox') as 'sandbox' | 'production';
  });
  
  // Token Info API Request/Response History
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
    if (activeTab === 'token-info') {
      loadTokenInfo();
    }
  }, [activeTab, environment]);

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
    if (totalTestingMode) {
      // Handle raw request
      if (!rawRequest.trim()) {
        setError('Raw request is required');
        return;
      }
      // TODO: Parse raw request and send
      setError('Total Testing Mode - raw request parsing not yet implemented');
      return;
    }

    if (!path) {
      setError('Path is required');
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
      setError(err.response?.data?.detail || 'Failed to make debug request');
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
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
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
                  {/* User Info */}
                  <div className="grid grid-cols-2 gap-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
                    <div>
                      <Label className="text-xs text-gray-500">User Email</Label>
                      <p className="font-semibold">{tokenInfo.user_email}</p>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-500">User ID</Label>
                      <p className="font-mono text-sm">{tokenInfo.user_id}</p>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-500">eBay Environment</Label>
                      <Badge variant={tokenInfo.ebay_environment === 'production' ? 'default' : 'secondary'}>
                        {tokenInfo.ebay_environment}
                      </Badge>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-500">Connection Status</Label>
                      <Badge variant={tokenInfo.ebay_connected ? 'default' : 'destructive'}>
                        {tokenInfo.ebay_connected ? 'Connected' : 'Not Connected'}
                      </Badge>
                    </div>
                    {tokenInfo.ebay_username && (
                      <div>
                        <Label className="text-xs text-gray-500">eBay Username</Label>
                        <p className="font-semibold">{tokenInfo.ebay_username}</p>
                      </div>
                    )}
                    {tokenInfo.ebay_user_id && (
                      <div>
                        <Label className="text-xs text-gray-500">eBay User ID</Label>
                        <p className="font-mono text-sm">{tokenInfo.ebay_user_id}</p>
                      </div>
                    )}
                  </div>

                  {/* Full Token */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm font-semibold">Full Access Token (Unmasked)</Label>
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

              {/* API Request/Response Terminal */}
              <Card className="mt-4">
                <CardHeader>
                  <CardTitle>📡 eBay API Request/Response Terminal</CardTitle>
                  <CardDescription>
                    Live API calls and response history. Automatically tests Identity API when token is loaded.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {/* Preview of next request */}
                  {tokenInfo && tokenInfo.token_full && (
                    <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
                      <div className="flex items-center justify-between mb-2">
                        <Label className="text-sm font-semibold">Next Request (when environment changes or refresh):</Label>
                        <Badge variant={environment === 'sandbox' ? 'default' : 'destructive'}>
                          {environment === 'sandbox' ? '🧪 Sandbox' : '🚀 Production'}
                        </Badge>
                      </div>
                      <div className="space-y-2 text-xs font-mono">
                        <div>
                          <span className="text-gray-600">Method:</span> <span className="font-bold text-green-700">GET</span>
                        </div>
                        <div>
                          <span className="text-gray-600">URL:</span>{' '}
                          <span className="text-blue-700">
                            {environment === 'sandbox' 
                              ? 'https://api.sandbox.ebay.com/identity/v1/oauth2/userinfo'
                              : 'https://api.ebay.com/identity/v1/oauth2/userinfo'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-600">Headers:</span>
                          <pre className="mt-1 p-2 bg-white rounded border text-xs overflow-auto">
{`Authorization: Bearer ${tokenInfo.token_full.substring(0, 30)}...${tokenInfo.token_full.substring(tokenInfo.token_full.length - 30)}
Accept: application/json
X-EBAY-C-MARKETPLACE-ID: EBAY_US`}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Request/Response History Terminal */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm font-semibold">Request/Response History ({tokenInfoHistory.length})</Label>
                      {tokenInfoHistory.length > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setTokenInfoHistory([]);
                            localStorage.removeItem('token_info_history');
                          }}
                        >
                          Clear History
                        </Button>
                      )}
                    </div>
                    <ScrollArea className="h-[400px] w-full rounded-md border bg-gray-900 p-4 font-mono text-xs">
                      {tokenInfoRequestLoading && (
                        <div className="text-yellow-400 mb-2">
                          ⏳ Testing Identity API...
                        </div>
                      )}
                      {tokenInfoHistory.length === 0 ? (
                        <div className="text-gray-400">
                          No API calls yet. Token info will automatically test Identity API when loaded.
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {tokenInfoHistory.map((entry, idx) => (
                            <div key={idx} className="border-b border-gray-700 pb-4 last:border-0">
                              <div className="text-gray-400 mb-2">
                                [{new Date(entry.timestamp).toLocaleString()}] {entry.environment === 'sandbox' ? '🧪' : '🚀'} {entry.environment.toUpperCase()}
                              </div>
                              
                              {/* Request */}
                              <div className="mb-3">
                                <div className="text-green-400 font-bold mb-1">→ REQUEST:</div>
                                <div className="text-green-300 ml-2">
                                  <div>{entry.request.method} {entry.request.url}</div>
                                  <div className="mt-1 text-gray-300">
                                    {Object.entries(entry.request.headers).map(([key, value]) => (
                                      <div key={key}>
                                        {key}: {key === 'Authorization' && value.startsWith('Bearer ') 
                                          ? `Bearer ${value.substring(7, 37)}...${value.substring(value.length - 30)}`
                                          : value}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              {/* Response */}
                              <div>
                                <div className={`font-bold mb-1 ${
                                  entry.response.status >= 200 && entry.response.status < 300 ? 'text-green-400' :
                                  entry.response.status >= 400 ? 'text-red-400' : 'text-yellow-400'
                                }`}>
                                  ← RESPONSE: {entry.response.status} {entry.response.status >= 200 && entry.response.status < 300 ? '✅' : '❌'}
                                </div>
                                <div className="text-gray-300 ml-2">
                                  <div className="mb-1">
                                    <span className="text-gray-400">Headers:</span>
                                    <pre className="mt-1 p-2 bg-gray-800 rounded text-xs overflow-auto max-h-32">
                                      {JSON.stringify(entry.response.headers, null, 2)}
                                    </pre>
                                  </div>
                                  <div>
                                    <span className="text-gray-400">Body:</span>
                                    <pre className="mt-1 p-2 bg-gray-800 rounded text-xs overflow-auto max-h-48">
                                      {typeof entry.response.body === 'object' 
                                        ? JSON.stringify(entry.response.body, null, 2)
                                        : String(entry.response.body)}
                                    </pre>
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
                  </div>
                </CardContent>
              </Card>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};
