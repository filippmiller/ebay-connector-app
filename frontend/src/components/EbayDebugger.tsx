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
import { Loader2, Play } from 'lucide-react';

interface DebugTemplate {
  name: string;
  description: string;
  method: string;
  path: string;
  params: Record<string, string>;
}

interface DebugResponse {
  request: {
    method: string;
    url: string;
    headers: Record<string, string>;
    params: Record<string, string>;
    body?: string;
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
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [method, setMethod] = useState<string>('GET');
  const [path, setPath] = useState<string>('');
  const [params, setParams] = useState<string>('');
  const [headers, setHeaders] = useState<string>('');
  const [body, setBody] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<DebugResponse | null>(null);
  const [error, setError] = useState<string>('');

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
      // Clear fields for custom request
      setMethod('GET');
      setPath('');
      setParams('');
      setHeaders('');
      setBody('');
    }
  };

  const handleDebug = async () => {
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

          {/* Error */}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Submit Button */}
          <Button onClick={handleDebug} disabled={loading || !path}>
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

      {/* Response */}
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
            <Tabs defaultValue="request" className="w-full">
              <TabsList>
                <TabsTrigger value="request">Request</TabsTrigger>
                <TabsTrigger value="response">Response</TabsTrigger>
                <TabsTrigger value="ebay-headers">eBay Headers</TabsTrigger>
              </TabsList>

              <TabsContent value="request" className="space-y-2">
                <div className="space-y-2">
                  <div>
                    <Label className="text-xs text-gray-500">Method</Label>
                    <p className="font-mono text-sm">{response.request.method}</p>
                  </div>
                  <div>
                    <Label className="text-xs text-gray-500">URL</Label>
                    <p className="font-mono text-sm break-all">{response.request.url}</p>
                  </div>
                  {Object.keys(response.request.params).length > 0 && (
                    <div>
                      <Label className="text-xs text-gray-500">Query Parameters</Label>
                      <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                        {JSON.stringify(response.request.params, null, 2)}
                      </pre>
                    </div>
                  )}
                  <div>
                    <Label className="text-xs text-gray-500">Headers</Label>
                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                      {JSON.stringify(response.request.headers, null, 2)}
                    </pre>
                  </div>
                  {response.request.body && (
                    <div>
                      <Label className="text-xs text-gray-500">Body</Label>
                      <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                        {typeof response.request.body === 'string' 
                          ? response.request.body 
                          : JSON.stringify(response.request.body, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="response" className="space-y-2">
                <div className="space-y-2">
                  <div>
                    <Label className="text-xs text-gray-500">Status</Label>
                    <p className="font-mono text-sm">
                      {response.response.status_code} {response.response.status_text}
                    </p>
                  </div>
                  <div>
                    <Label className="text-xs text-gray-500">Response Body</Label>
                    <ScrollArea className="h-96 w-full rounded-md border bg-gray-50 p-4">
                      <pre className="text-xs font-mono overflow-auto">
                        {typeof response.response.body === 'string'
                          ? response.response.body
                          : JSON.stringify(response.response.body, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                  {response.response.status_code >= 400 && (
                    <Alert variant="destructive">
                      <AlertDescription>
                        {typeof response.response.body === 'object' && response.response.body.errors
                          ? JSON.stringify(response.response.body.errors, null, 2)
                          : 'Request failed. Check response body for details.'}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="ebay-headers" className="space-y-2">
                <div className="space-y-2">
                  <Label className="text-xs text-gray-500">eBay-Specific Headers</Label>
                  {Object.keys(response.response.ebay_headers).length > 0 ? (
                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                      {JSON.stringify(response.response.ebay_headers, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-xs text-gray-500">No eBay-specific headers found</p>
                  )}
                  <div className="mt-4">
                    <Label className="text-xs text-gray-500">All Headers</Label>
                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                      {JSON.stringify(response.response.headers, null, 2)}
                    </pre>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

