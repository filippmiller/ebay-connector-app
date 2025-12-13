import React, { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import api from '@/lib/apiClient';

interface FlowListItem {
  flow_key: string;
  title: string;
  summary?: string | null;
  category?: string | null;
  keywords?: string[];
  generated_at?: string | null;
  updated_at?: string | null;
}

interface FlowListResponse {
  rows: FlowListItem[];
  total: number;
  limit: number;
  offset: number;
}

interface FlowDetail {
  flow_key: string;
  title: string;
  summary?: string | null;
  category?: string | null;
  keywords: string[];
  graph: {
    nodes: Record<string, any>;
    edges: Array<{ from: string; to: string; label?: string }>;
  };
  source: Record<string, any>;
  generated_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export default function AdminEbayFlowsPage() {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState<string>('');

  const [list, setList] = useState<FlowListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<FlowDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const r of list) {
      if (r.category) s.add(r.category);
    }
    return Array.from(s).sort();
  }, [list]);

  const loadList = async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await api.get<FlowListResponse>('/api/admin/ebay-flows', {
        params: {
          q: q.trim() || undefined,
          category: category || undefined,
          limit: 100,
          offset: 0,
        },
      });
      setList(resp.data.rows || []);
      setTotal(resp.data.total || 0);
      if (!selectedKey && resp.data.rows && resp.data.rows.length > 0) {
        setSelectedKey(resp.data.rows[0].flow_key);
      }
    } catch (e: any) {
      console.error('Failed to load flow catalog', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to load flow catalog');
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (flowKey: string) => {
    try {
      setDetailLoading(true);
      setDetailError(null);
      const resp = await api.get<FlowDetail>(`/api/admin/ebay-flows/${encodeURIComponent(flowKey)}`);
      setDetail(resp.data);
    } catch (e: any) {
      console.error('Failed to load flow detail', e);
      setDetailError(e?.response?.data?.detail || e.message || 'Failed to load flow detail');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const regenerate = async () => {
    try {
      setError(null);
      await api.post('/api/admin/ebay-flows/regenerate');
      await loadList();
      if (selectedKey) {
        await loadDetail(selectedKey);
      }
    } catch (e: any) {
      console.error('Failed to regenerate', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to regenerate flows');
    }
  };

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedKey) void loadDetail(selectedKey);
  }, [selectedKey]);

  const nodeLabel = (key: string) => {
    const n = detail?.graph?.nodes?.[key];
    return (n?.label as string) || key;
  };

  const edgesPreview = useMemo(() => {
    const edges = detail?.graph?.edges || [];
    return edges.map((e, idx) => {
      const from = nodeLabel(e.from);
      const to = nodeLabel(e.to);
      const label = e.label ? ` (${e.label})` : '';
      return `${from} → ${to}${label}`;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  const nodesTable = useMemo(() => {
    const nodes = detail?.graph?.nodes || {};
    return Object.entries(nodes).map(([k, v]) => ({ key: k, ...(v as any) }));
  }, [detail]);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
        <div className="flex items-center justify-between gap-2 mb-4">
          <h1 className="text-2xl font-bold">Admin → eBay Flow Catalog</h1>
          <Button variant="secondary" onClick={regenerate} disabled={loading}>
            Regenerate (auto)
          </Button>
        </div>

        <Card className="mb-4">
          <CardHeader>
            <CardTitle>Search</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col md:flex-row gap-2">
              <Input
                placeholder="Search: sold, transactions, listing, GetSellerTransactions, tbl_parts_inventory..."
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void loadList();
                }}
              />
              <Input
                placeholder="Category (optional)"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                list="flow-categories"
              />
              <datalist id="flow-categories">
                {categories.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
              <Button onClick={loadList} disabled={loading}>
                Apply
              </Button>
            </div>
            <div className="text-sm text-gray-600 mt-2">
              Total: <span className="font-mono">{total}</span>
            </div>
            {error && <div className="text-sm text-red-600 mt-2">{error}</div>}
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>Flows</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="text-sm">Loading…</div>
              ) : (
                <div className="flex flex-col gap-2">
                  {list.map((r) => (
                    <button
                      key={r.flow_key}
                      className={
                        'text-left p-3 rounded border ' +
                        (selectedKey === r.flow_key ? 'border-blue-400 bg-blue-50' : 'border-gray-200 bg-white')
                      }
                      onClick={() => setSelectedKey(r.flow_key)}
                    >
                      <div className="font-semibold">{r.title}</div>
                      <div className="text-xs text-gray-600 font-mono">{r.flow_key}</div>
                      {r.summary && <div className="text-sm text-gray-700 mt-1">{r.summary}</div>}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {r.category && <Badge variant="secondary">{r.category}</Badge>}
                        {(r.keywords || []).slice(0, 5).map((k) => (
                          <Badge key={k} variant="outline">{k}</Badge>
                        ))}
                      </div>
                    </button>
                  ))}
                  {list.length === 0 && <div className="text-sm text-gray-600">No flows found.</div>}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent>
              {!selectedKey && <div className="text-sm text-gray-600">Select a flow on the left.</div>}

              {detailLoading && <div className="text-sm">Loading detail…</div>}
              {detailError && <div className="text-sm text-red-600">{detailError}</div>}

              {detail && !detailLoading && (
                <div className="space-y-4">
                  <div>
                    <div className="text-xl font-bold">{detail.title}</div>
                    <div className="text-xs text-gray-600 font-mono">{detail.flow_key}</div>
                    {detail.summary && <div className="text-sm text-gray-700 mt-1">{detail.summary}</div>}
                    <div className="mt-2 flex flex-wrap gap-1">
                      {detail.category && <Badge variant="secondary">{detail.category}</Badge>}
                      {(detail.keywords || []).map((k) => (
                        <Badge key={k} variant="outline">{k}</Badge>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="font-semibold mb-1">Flow (arrows)</div>
                    <pre className="text-xs bg-gray-100 p-3 rounded overflow-auto">
{edgesPreview.join('\n')}
                    </pre>
                  </div>

                  <div>
                    <div className="font-semibold mb-1">Nodes</div>
                    <div className="overflow-auto">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-600">
                            <th className="py-1 pr-3">key</th>
                            <th className="py-1 pr-3">type</th>
                            <th className="py-1 pr-3">label</th>
                            <th className="py-1 pr-3">table</th>
                          </tr>
                        </thead>
                        <tbody>
                          {nodesTable.map((n) => (
                            <tr key={n.key} className="border-t">
                              <td className="py-1 pr-3 font-mono text-xs">{n.key}</td>
                              <td className="py-1 pr-3">{n.type || ''}</td>
                              <td className="py-1 pr-3">{n.label || ''}</td>
                              <td className="py-1 pr-3 font-mono text-xs">{n.table || ''}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div>
                    <div className="font-semibold mb-1">Generator metadata</div>
                    <pre className="text-xs bg-gray-100 p-3 rounded overflow-auto">
{JSON.stringify(detail.source || {}, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
