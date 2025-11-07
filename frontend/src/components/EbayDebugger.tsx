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

  useEffect(() => {
    loadTemplates();
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
      <Card>
        <CardHeader>
          <CardTitle>🔧 eBay API Debugger</CardTitle>
          <CardDescription>
            Test eBay API requests directly. Check token validity, diagnose errors, and see full request/response data.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
                placeholder="GET https://api.ebay.com/identity/v1/oauth2/userinfo&#10;Authorization: Bearer v^1.1#...&#10;X-EBAY-C-MARKETPLACE-ID: EBAY_US"
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
    </div>
  );
};
